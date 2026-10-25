import argparse
import logging
import os
import re
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database.connection import postgres_connection_params
from app.features.system.backup_crypto import decrypt_backup
from app.features.system.backup_manifest import (
    validate_manifest,
    validate_manifest_file,
)
from app.shared.sql_text import sql_lines

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    from scripts.database_migration_config import quote_identifier
except ModuleNotFoundError:
    from database_migration_config import quote_identifier

DEFAULT_DML_PATH = ROOT_DIR / "scripts" / "data_inserts_postgresql.sql"
FILENAME_SPE_DUMP = "spe_dump.sql"
FILENAME_SPE_DB = "spe-db.sql"
MAX_SQL_BYTES = 2 * 1024 * 1024 * 1024
MAX_STATEMENT_BYTES = 128 * 1024 * 1024

TRANSACTION_KEYWORDS = {"BEGIN", "COMMIT", "END", "ROLLBACK"}
ALLOWED_SET_NAMES = {
    "client_encoding",
    "standard_conforming_strings",
    "check_function_bodies",
    "client_min_messages",
    "row_security",
    "search_path",
    "default_tablespace",
    "default_table_access_method",
    "xmloption",
    "default_with_oids",
    "lock_timeout",
    "statement_timeout",
    "idle_in_transaction_session_timeout",
    "transaction_timeout",
    "constraints",
}


def load_environment() -> None:
    env_path = ROOT_DIR / ".env"
    if env_path.exists() and load_dotenv:
        load_dotenv(dotenv_path=env_path, override=False)


def get_pg_credentials() -> dict[str, str]:
    load_environment()
    return {
        key: str(value) for key, value in postgres_connection_params(
            os.getenv("SQLALCHEMY_DATABASE_URI", ""), os.environ,
        ).items()
    }


def connect_with_retry(
    creds: dict[str, str],
    max_retries: int = 30,
    delay: float = 1.0,
) -> Any:
    if psycopg2 is None:
        raise RuntimeError("Driver psycopg2 não está instalado.")

    for attempt in range(1, max_retries + 1):
        try:
            return psycopg2.connect(
                host=creds["host"],
                port=int(creds["port"]),
                user=creds["user"],
                password=creds["password"],
                dbname=creds["dbname"],
                connect_timeout=5,
            )
        except psycopg2.OperationalError as exc:
            if attempt == max_retries:
                raise RuntimeError(
                    f"Não foi possível conectar ao PostgreSQL após {max_retries} tentativas: {exc}"
                ) from exc
            time.sleep(delay)
    raise RuntimeError("Falha inesperada ao conectar ao PostgreSQL")


def _dollar_tag_at(sql: str, offset: int) -> str | None:
    match = re.match(r"\$(?:[^\W\d]\w*)?\$", sql[offset:])
    return match.group(0) if match else None


def _step_comment(char, next_char, buffer, state):
    if state == "line_comment":
        return ("normal" if char == "\n" else state), 0
    if char == "*" and next_char == "/":
        buffer.append(next_char)
        return "normal", 1
    return state, 0


def _step_quoted(char, next_char, buffer, state, escape_string):
    if state == "single_quote" and char == "\\" and escape_string and next_char:
        buffer.append(next_char)
        return state, 1
    closing_quote = "'" if state == "single_quote" else '"'
    if char != closing_quote:
        return state, 0
    if next_char == closing_quote:
        buffer.append(next_char)
        return state, 1
    return "normal", 0


def _step_dollar_quote(sql, index, char, buffer, dollar_tag):
    if char == "$" and dollar_tag and sql.startswith(dollar_tag, index):
        buffer.extend(dollar_tag[1:])
        return "normal", None, len(dollar_tag) - 1
    return "dollar_quote", dollar_tag, 0


def _step_normal(sql, index, char, next_char, buffer):
    if char == "-" and next_char == "-":
        buffer.append(next_char)
        return "line_comment", None, False, 1
    if char == "/" and next_char == "*":
        buffer.append(next_char)
        return "block_comment", None, False, 1
    if char == "'":
        previous = sql[index - 1] if index else ""
        return "single_quote", None, previous in {"e", "E"}, 0
    if char == '"':
        return "double_quote", None, False, 0
    if char == "$":
        tag = _dollar_tag_at(sql, index)
        if tag:
            buffer.extend(tag[1:])
            return "dollar_quote", tag, False, len(tag) - 1
    return "normal", None, False, 0


def _step_split(sql, index, char, next_char, state, dollar_tag,
                escape_string, buffer, statements):
    if state in {"line_comment", "block_comment"}:
        state, consumed = _step_comment(char, next_char, buffer, state)
    elif state in {"single_quote", "double_quote"}:
        state, consumed = _step_quoted(char, next_char, buffer, state, escape_string)
    elif state == "dollar_quote":
        state, dollar_tag, consumed = _step_dollar_quote(
            sql, index, char, buffer, dollar_tag
        )
    elif char == ";":
        statement = "".join(buffer).strip()
        if statement:
            statements.append(statement)
        buffer = []
        consumed = 0
    else:
        state, dollar_tag, escape_string, consumed = _step_normal(
            sql, index, char, next_char, buffer
        )
    return state, dollar_tag, escape_string, buffer, consumed


def split_sql_statements(
    sql: str, *, complete_only: bool = False,
) -> list[str] | tuple[list[str], str]:
    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    state = "normal"
    dollar_tag: str | None = None
    escape_string = False

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        buffer.append(char)
        state, dollar_tag, escape_string, buffer, consumed = _step_split(
            sql, index, char, next_char, state, dollar_tag,
            escape_string, buffer, statements,
        )
        index += consumed + 1

    if complete_only:
        return statements, "".join(buffer)
    if state in {"single_quote", "double_quote", "block_comment", "dollar_quote"}:
        raise ValueError("SQL inválido ou truncado: literal/comentário não foi fechado")
    remainder = "".join(buffer).strip()
    if remainder:
        statements.append(remainder)
    return statements


def strip_sql_comments(sql: str) -> str:
    output: list[str] = []
    index = 0
    state = "normal"
    dollar_tag: str | None = None
    escape_string = False
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        state, dollar_tag, escape_string, consumed = _strip_step(
            sql, index, char, next_char, output, state, dollar_tag, escape_string
        )
        index += consumed
        index += 1
    if state in {"single_quote", "double_quote", "block_comment", "dollar_quote"}:
        raise ValueError("SQL inválido ou truncado: literal/comentário não foi fechado")
    return "".join(output)


def _strip_comment_step(char, next_char, output, state, dollar_tag, escape_string):
    if state == "line_comment":
        if char == "\n":
            output.append(char)
            state = "normal"
        return state, dollar_tag, escape_string, 0
    if char == "\n":
        output.append(char)
    if char == "*" and next_char == "/":
        return "normal", dollar_tag, escape_string, 1
    return state, dollar_tag, escape_string, 0


def _strip_quoted_step(char, next_char, output, state, dollar_tag, escape_string):
    output.append(char)
    state, consumed = _step_quoted(char, next_char, output, state, escape_string)
    return state, dollar_tag, escape_string, consumed


def _strip_dollar_step(sql, index, char, output, dollar_tag, escape_string):
    if dollar_tag and sql.startswith(dollar_tag, index):
        output.append(dollar_tag)
        return "normal", None, escape_string, len(dollar_tag) - 1
    output.append(char)
    return "dollar_quote", dollar_tag, escape_string, 0


def _strip_normal_step(sql, index, char, next_char, output, dollar_tag, escape_string):
    if char == "-" and next_char == "-":
        return "line_comment", dollar_tag, escape_string, 1
    if char == "/" and next_char == "*":
        return "block_comment", dollar_tag, escape_string, 1
    if char == "'":
        output.append(char)
        previous = sql[index - 1] if index else ""
        return "single_quote", dollar_tag, previous in {"e", "E"}, 0
    if char == '"':
        output.append(char)
        return "double_quote", dollar_tag, False, 0
    if char == "$":
        tag = _dollar_tag_at(sql, index)
        if tag:
            output.append(tag)
            return "dollar_quote", tag, escape_string, len(tag) - 1
    output.append(char)
    return "normal", dollar_tag, escape_string, 0


def _strip_step(sql, index, char, next_char, output, state, dollar_tag, escape_string):
    if state in {"line_comment", "block_comment"}:
        return _strip_comment_step(
            char, next_char, output, state, dollar_tag, escape_string
        )
    if state in {"single_quote", "double_quote"}:
        return _strip_quoted_step(char, next_char, output, state, dollar_tag, escape_string)
    if state == "dollar_quote":
        return _strip_dollar_step(sql, index, char, output, dollar_tag, escape_string)
    return _strip_normal_step(
        sql, index, char, next_char, output, dollar_tag, escape_string
    )


def _without_leading_comments(statement: str) -> str:
    result = statement.lstrip()
    while True:
        if result.startswith("--"):
            newline = result.find("\n")
            return "" if newline < 0 else _without_leading_comments(result[newline + 1:])
        if result.startswith("/*"):
            end = result.find("*/", 2)
            if end < 0:
                return ""
            result = result[end + 2:].lstrip()
            continue
        return result


def _unquote_identifier(identifier: str) -> str:
    identifier = identifier.strip()
    if identifier.startswith('"') and identifier.endswith('"'):
        return identifier[1:-1].replace('""', '"')
    return identifier.lower()


def _insert_target(statement: str) -> tuple[str | None, str]:
    quoted_identifier = r'"(?:""|[^"])+"'
    identifier = rf"(?:{quoted_identifier}|[^\W\d][\w$]*)"
    match = re.match(
        rf"(?s)^INSERT\s+INTO\s+(?:({identifier})\s*\.\s*)?({identifier})",
        statement,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("Não foi possível identificar a tabela de um INSERT")
    schema = _unquote_identifier(match.group(1)) if match.group(1) else None
    return schema, _unquote_identifier(match.group(2))


def _prepare_insert(statement: str, insert_tables: set[str]) -> str | None:
    schema, table = _insert_target(statement)
    if schema not in (None, "public"):
        raise ValueError(f"INSERT fora do schema public não é permitido: {schema}.{table}")
    if table == "alembic_version":
        return None
    insert_tables.add(table)
    return statement


def _prepare_select(statement: str) -> str | None:
    if re.match(r"(?is)^SELECT\s+(?:pg_catalog\.)?set_config\s*\(", statement):
        return None
    if re.match(r"(?is)^SELECT\s+(?:pg_catalog\.)?setval\s*\(", statement):
        return statement
    raise ValueError(f"SELECT não permitido em dump de dados: {statement[:100]!r}")


def _prepare_set(statement: str) -> str | None:
    setting_match = re.match(
        r"(?s)^SET\s+(?:SESSION\s+|LOCAL\s+)?(\w+)", statement.upper()
    )
    setting = setting_match.group(1).lower() if setting_match else ""
    if setting not in ALLOWED_SET_NAMES:
        raise ValueError(f"SET não permitido em dump de dados: {setting or statement[:80]}")
    return None if setting in {"search_path", "client_encoding", "standard_conforming_strings"} else statement


def _prepare_statement(statement: str, insert_tables: set[str]) -> str | None:
    first_match = re.match(r"^([A-Z]+)", statement.upper())
    if not first_match:
        raise ValueError(f"Comando SQL não reconhecido: {statement[:80]!r}")
    keyword = first_match.group(1).upper()
    if keyword in TRANSACTION_KEYWORDS:
        return None
    if keyword == "START" and re.match(r"(?is)^START\s+TRANSACTION\b", statement):
        return None
    handlers = {"INSERT": _prepare_insert, "SELECT": _prepare_select, "SET": _prepare_set}
    handler = handlers.get(keyword)
    if handler is not None:
        return handler(statement, insert_tables) if keyword == "INSERT" else handler(statement)
    raise ValueError(
        f"Dump deve conter somente INSERT/SET/setval; comando {keyword} não é permitido"
    )


def prepare_data_statements(
    sql_content: str, *, allow_empty: bool = False,
) -> tuple[list[str], set[str]]:
    cleaned_sql = "".join(sql_lines(
        sql_content.splitlines(keepends=True), reject_psql_commands=True,
    ))

    prepared: list[str] = []
    insert_tables: set[str] = set()
    for raw_statement in split_sql_statements(cleaned_sql):
        statement = _without_leading_comments(raw_statement)
        if not statement:
            continue
        candidate = _prepare_statement(statement, insert_tables)
        if candidate is not None:
            prepared.append(candidate)

    if not prepared and not allow_empty:
        raise ValueError("O arquivo não contém comandos de dados aplicáveis")
    return prepared, insert_tables


def extract_dump_alembic_revisions(sql_content: str) -> set[str]:
    revisions: set[str] = set()
    for raw_statement in split_sql_statements(sql_content):
        statement = _without_leading_comments(raw_statement)
        if not re.match(r"(?is)^INSERT\s+INTO\b", statement):
            continue
        schema, table = _insert_target(statement)
        if schema not in (None, "public") or table != "alembic_version":
            continue
        match = re.search(r"(?is)\bVALUES\s*\(\s*'((?:''|[^'])*)'", statement)
        if not match:
            raise ValueError("Não foi possível ler a revisão Alembic contida no backup")
        revisions.add(match.group(1).replace("''", "'"))
    return revisions


def _public_tables(cursor: Any) -> list[str]:
    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    )
    return [row[0] for row in cursor.fetchall()]


def _validate_target_schema(
    cursor: Any,
    insert_tables: set[str],
    dump_revisions: set[str],
) -> tuple[list[str], set[str]]:
    tables = _public_tables(cursor)
    if "alembic_version" not in tables:
        raise RuntimeError("Schema ausente: execute as migrações Alembic antes do restore")
    cursor.execute("SELECT version_num FROM alembic_version ORDER BY version_num")
    revisions = {row[0] for row in cursor.fetchall()}
    if not revisions:
        raise RuntimeError("alembic_version está vazia; o schema de destino não foi validado")
    compatible_prior_revisions = {("001", "002"), ("003", "004")}
    compatible = len(dump_revisions) == len(revisions) == 1 and (
        next(iter(dump_revisions)), next(iter(revisions))
    ) in compatible_prior_revisions
    if dump_revisions and dump_revisions != revisions and not compatible:
        raise RuntimeError(
            "Revisão Alembic do backup não corresponde ao destino: "
            f"backup={sorted(dump_revisions)}, destino={sorted(revisions)}"
        )

    application_tables = [table for table in tables if table != "alembic_version"]
    unknown_tables = sorted(insert_tables - set(application_tables))
    if unknown_tables:
        raise RuntimeError(
            "Dump contém tabelas ausentes no PostgreSQL: " + ", ".join(unknown_tables)
        )
    return application_tables, revisions


def _truncate_database_tables(cursor: Any, table_names: list[str]) -> None:
    if not table_names:
        return
    qualified = ", ".join(
        f"{quote_identifier('public')}.{quote_identifier(table)}" for table in table_names
    )
    cursor.execute(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE")


def _check_sql_file(sql_path: Path) -> None:
    if not sql_path.is_file():
        raise FileNotFoundError(f"Arquivo SQL não encontrado: {sql_path}")
    if sql_path.stat().st_size > MAX_SQL_BYTES:
        raise ValueError(f"Arquivo SQL excede o limite de {MAX_SQL_BYTES} bytes")


def _execute_statements(cursor, statement_factory, statement_count: int) -> None:
    executed = 0
    for statement in statement_factory():
        cursor.execute(statement)
        executed += 1
    if executed != statement_count:
        raise RuntimeError("Dump foi alterado durante a restauração")


def _validate_applied_row_counts(cursor, application_tables, validator, expected_counts) -> None:
    if expected_counts is None:
        return
    if validator(set(application_tables)) != expected_counts:
        raise RuntimeError("Manifesto do backup foi alterado durante a restauração")
    for table, expected_count in expected_counts.items():
        cursor.execute(f'SELECT COUNT(*) FROM public.{quote_identifier(table)}')
        actual_count = cursor.fetchone()[0]
        if actual_count != expected_count:
            raise RuntimeError(
                f"Backup incompleto na tabela {table}: esperado {expected_count}, aplicado {actual_count}"
            )


def _validate_restore_target(cursor, insert_tables, dump_revisions,
                             manifest_validator, truncate_first, expected_database):
    cursor.execute("SELECT current_database()")
    current_database = cursor.fetchone()[0]
    if expected_database and current_database != expected_database:
        raise RuntimeError(
            f"Banco conectado é {current_database!r}, mas {expected_database!r} foi confirmado"
        )
    application_tables, target_revisions = _validate_target_schema(
        cursor, insert_tables, dump_revisions
    )
    row_counts = manifest_validator(set(application_tables)) if truncate_first else None
    result = {
        "database": current_database,
        "statements": None,
        "insert_tables": sorted(insert_tables),
        "alembic_revisions": sorted(target_revisions),
        "truncated_tables": application_tables if truncate_first else [],
    }
    return application_tables, row_counts, result


def _execute_restore(cursor, statement_factory, statement_count, application_tables,
                     manifest_validator, row_counts, truncate_first):
    cursor.execute("SELECT pg_advisory_xact_lock(hashtext('spe:data_restore'))")
    cursor.execute("SET LOCAL search_path = public, pg_catalog")
    cursor.execute("SET LOCAL standard_conforming_strings = on")
    if truncate_first:
        _truncate_database_tables(cursor, application_tables)
    cursor.execute("SET CONSTRAINTS ALL DEFERRED")
    _execute_statements(cursor, statement_factory, statement_count)
    _validate_applied_row_counts(
        cursor, application_tables, manifest_validator, row_counts
    )


def _iter_sql_file_statements(sql_path: Path) -> Iterator[str]:
    remainder = ""
    with sql_path.open("r", encoding="utf-8") as source:
        for line in sql_lines(source, reject_psql_commands=True):
            remainder += line
            if len(remainder.encode("utf-8")) > MAX_STATEMENT_BYTES:
                raise ValueError(f"Comando SQL excede {MAX_STATEMENT_BYTES} bytes")
            if ";" not in line:
                continue
            complete, remainder = split_sql_statements(remainder, complete_only=True)
            yield from complete
    if remainder.strip():
        yield from split_sql_statements(remainder)


def _iter_prepared_file_statements(sql_path: Path) -> Iterator[str]:
    for raw_statement in _iter_sql_file_statements(sql_path):
        prepared, _ = prepare_data_statements(raw_statement, allow_empty=True)
        yield from prepared


def _apply_prepared_dump(
    statement_factory: Callable[[], Iterator[str]],
    statement_count: int,
    insert_tables: set[str],
    dump_revisions: set[str],
    manifest_validator: Callable[[set[str]], dict[str, int] | None],
    *,
    truncate_first: bool,
    allow_destructive: bool,
    expected_database: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    if truncate_first and not allow_destructive and not dry_run:
        raise RuntimeError("Restauração destrutiva não confirmada; use --yes")

    creds = get_pg_credentials()
    connection = connect_with_retry(creds)
    connection.autocommit = False
    cursor = connection.cursor()
    try:
        application_tables, row_counts, result = _validate_restore_target(
            cursor, insert_tables, dump_revisions, manifest_validator,
            truncate_first, expected_database,
        )
        result["statements"] = statement_count
        if dry_run:
            connection.rollback()
            result["truncated_tables"] = []
            return result
        _execute_restore(
            cursor, statement_factory, statement_count, application_tables,
            manifest_validator, row_counts, truncate_first,
        )
        connection.commit()
        return result
    except Exception as exc:
        logging.getLogger(__name__).exception("Falha na operação", exc_info=False)
        connection.rollback()
        raise RuntimeError(f"Falha ao aplicar SQL no PostgreSQL: {exc}") from exc
    finally:
        cursor.close()
        connection.close()


def apply_sql_content(
    sql_content: str,
    *,
    truncate_first: bool = True,
    allow_destructive: bool = False,
    expected_database: str | None = None,
    dry_run: bool = False,
    allow_unverified_dump: bool = False,
) -> dict[str, Any]:
    dump_revisions = extract_dump_alembic_revisions(sql_content)
    statements, insert_tables = prepare_data_statements(sql_content)
    return _apply_prepared_dump(
        lambda: iter(statements), len(statements), insert_tables, dump_revisions,
        lambda tables: validate_manifest(
            sql_content, tables, allow_unverified=allow_unverified_dump,
        ),
        truncate_first=truncate_first,
        allow_destructive=allow_destructive,
        expected_database=expected_database,
        dry_run=dry_run,
    )


def apply_sql_file(
    sql_path: Path,
    truncate_first: bool = True,
    *,
    allow_destructive: bool = False,
    expected_database: str | None = None,
    dry_run: bool = False,
    allow_unverified_dump: bool = False,
) -> dict[str, Any]:
    _check_sql_file(sql_path)
    statement_count = 0
    insert_tables: set[str] = set()
    dump_revisions: set[str] = set()
    for raw_statement in _iter_sql_file_statements(sql_path):
        dump_revisions.update(extract_dump_alembic_revisions(raw_statement))
        prepared, tables = prepare_data_statements(raw_statement, allow_empty=True)
        statement_count += len(prepared)
        insert_tables.update(tables)
    if not statement_count:
        raise ValueError("O arquivo não contém comandos de dados aplicáveis")
    return _apply_prepared_dump(
        lambda: _iter_prepared_file_statements(sql_path),
        statement_count,
        insert_tables,
        dump_revisions,
        lambda tables: validate_manifest_file(
            sql_path, tables, allow_unverified=allow_unverified_dump,
        ),
        truncate_first=truncate_first,
        allow_destructive=allow_destructive,
        expected_database=expected_database,
        dry_run=dry_run,
    )


def _find_data_member(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    files = [item for item in archive.infolist() if not item.is_dir()]
    by_basename = {Path(item.filename).name: item for item in files}
    for name in (FILENAME_SPE_DUMP, "data.sql", "data_inserts_postgresql.sql"):
        if name in by_basename:
            return by_basename[name]
    sql_files = [item for item in files if item.filename.lower().endswith(".sql")]
    sql_files = [item for item in sql_files if Path(item.filename).name != FILENAME_SPE_DB]
    if len(sql_files) == 1:
        return sql_files[0]
    raise FileNotFoundError("Nenhum dump de dados SQL inequívoco foi encontrado no ZIP")


def find_backup_source() -> Path | None:
    candidates = [
        ROOT_DIR / "scripts" / "spe.zip.enc",
        ROOT_DIR / "spe.zip.enc",
        ROOT_DIR / "scripts" / "spe.zip",
        ROOT_DIR / "spe.zip",
        ROOT_DIR / FILENAME_SPE_DUMP,
        ROOT_DIR / "scripts" / FILENAME_SPE_DUMP,
        DEFAULT_DML_PATH,
    ]
    return next((path for path in candidates if path.is_file()), None)


def restore_backup(
    source_path: Path | None = None,
    *,
    allow_destructive: bool = False,
    expected_database: str | None = None,
    dry_run: bool = False,
    allow_unverified_dump: bool = False,
) -> dict[str, Any]:
    target = source_path or find_backup_source()
    if not target or not target.is_file():
        raise FileNotFoundError("Arquivo de backup ou dump não encontrado")

    if target.name.endswith(".zip.enc"):
        return _restore_encrypted_backup(
            target, allow_destructive, expected_database, dry_run, allow_unverified_dump
        )

    if target.suffix.lower() != ".zip":
        return _apply_backup_sql(
            target, allow_destructive, expected_database, dry_run, allow_unverified_dump
        )

    return _restore_zip_backup(
        target, allow_destructive, expected_database, dry_run, allow_unverified_dump
    )


def _restore_encrypted_backup(target, allow_destructive, expected_database,
                              dry_run, allow_unverified_dump):
    load_environment()
    decrypted = decrypt_backup(target, os.getenv("SECRET_KEY", ""))
    try:
        return restore_backup(
            decrypted,
            allow_destructive=allow_destructive,
            expected_database=expected_database,
            dry_run=dry_run,
            allow_unverified_dump=allow_unverified_dump,
        )
    finally:
        decrypted.unlink(missing_ok=True)


def _apply_backup_sql(target, allow_destructive, expected_database,
                      dry_run, allow_unverified_dump):
    return apply_sql_file(
        target,
        allow_destructive=allow_destructive,
        expected_database=expected_database,
        dry_run=dry_run,
        allow_unverified_dump=allow_unverified_dump,
    )


def _restore_zip_backup(target, allow_destructive, expected_database,
                        dry_run, allow_unverified_dump):

    with zipfile.ZipFile(target, "r") as archive:
        member = _find_data_member(archive)
        if member.file_size > MAX_SQL_BYTES:
            raise ValueError(f"SQL compactado excede o limite de {MAX_SQL_BYTES} bytes")
        with tempfile.NamedTemporaryFile(prefix="spe-sql-", suffix=".sql", delete=False) as output:
            temporary = Path(output.name)
            try:
                with archive.open(member) as source:
                    copied = 0
                    while chunk := source.read(1024 * 1024):
                        copied += len(chunk)
                        if copied > MAX_SQL_BYTES:
                            raise ValueError(f"SQL compactado excede o limite de {MAX_SQL_BYTES} bytes")
                        output.write(chunk)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
    return _apply_temporary_dump(
        temporary, allow_destructive, expected_database, dry_run, allow_unverified_dump
    )


def _apply_temporary_dump(temporary, allow_destructive, expected_database,
                          dry_run, allow_unverified_dump):
    try:
        return _apply_backup_sql(
            temporary, allow_destructive, expected_database, dry_run, allow_unverified_dump
        )
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Valida e aplica um dump somente de dados no PostgreSQL, preservando o schema."
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_DML_PATH, help="Arquivo SQL ou ZIP")
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Busca automaticamente spe.zip/spe_dump.sql quando --file não for informado",
    )
    parser.add_argument("--no-truncate", action="store_true", help="Insere sem limpar os dados atuais")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma que todos os dados das tabelas public podem ser apagados",
    )
    parser.add_argument(
        "--confirm-database",
        help="Exige que o nome real do banco seja exatamente este antes de apagar dados",
    )
    parser.add_argument("--dry-run", action="store_true", help="Valida arquivo, conexão e schema sem alterar dados")
    parser.add_argument(
        "--allow-unverified-dump", action="store_true",
        help="Aceita backup antigo sem manifesto; use somente após verificar a origem e a integridade",
    )
    args = parser.parse_args()

    if not args.no_truncate and not args.yes and not args.dry_run:
        parser.error("a restauração apaga os dados atuais; informe --yes")

    try:
        source = None if args.restore and args.file == DEFAULT_DML_PATH else args.file
        if args.restore:
            result = restore_backup(
                source,
                allow_destructive=args.yes,
                expected_database=args.confirm_database,
                dry_run=args.dry_run,
                allow_unverified_dump=args.allow_unverified_dump,
            )
        else:
            result = apply_sql_file(
                args.file,
                truncate_first=not args.no_truncate,
                allow_destructive=args.yes,
                expected_database=args.confirm_database,
                dry_run=args.dry_run,
                allow_unverified_dump=args.allow_unverified_dump,
            )
        action = "validado" if args.dry_run else "aplicado"
        print(
            f"Dump {action} com sucesso em {result['database']}: "
            f"{result['statements']} comandos, {len(result['insert_tables'])} tabelas com dados."
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("Falha na operação", exc_info=False)
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
