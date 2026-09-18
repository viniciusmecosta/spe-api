import argparse
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

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

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DML_PATH = ROOT_DIR / "scripts" / "data_inserts_postgresql.sql"
FILENAME_SPE_DUMP = "spe_dump.sql"
FILENAME_SPE_DB = "spe-db.sql"
MAX_SQL_BYTES = 2 * 1024 * 1024 * 1024

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
    uri = os.getenv("SQLALCHEMY_DATABASE_URI", "")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    dbname = os.getenv("POSTGRES_DB")

    if uri and (not host or not user or not dbname):
        try:
            from sqlalchemy.engine import make_url

            parsed = make_url(uri)
            host = host or parsed.host
            port = port or (str(parsed.port) if parsed.port else None)
            user = user or parsed.username
            password = password if password is not None else parsed.password
            dbname = dbname or parsed.database
        except Exception:
            pass

    return {
        "host": host or "localhost",
        "port": port or "5432",
        "user": user or "spe",
        "password": password or "",
        "dbname": dbname or "spe_db",
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
    match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[offset:])
    return match.group(0) if match else None


def split_sql_statements(sql: str) -> list[str]:
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

        if state == "line_comment":
            if char == "\n":
                state = "normal"
        elif state == "block_comment":
            if char == "*" and next_char == "/":
                buffer.append(next_char)
                index += 1
                state = "normal"
        elif state == "single_quote":
            if char == "\\" and escape_string and next_char:
                buffer.append(next_char)
                index += 1
            elif char == "'":
                if next_char == "'":
                    buffer.append(next_char)
                    index += 1
                else:
                    state = "normal"
        elif state == "double_quote":
            if char == '"':
                if next_char == '"':
                    buffer.append(next_char)
                    index += 1
                else:
                    state = "normal"
        elif state == "dollar_quote":
            if dollar_tag and sql.startswith(dollar_tag, index):
                for extra in dollar_tag[1:]:
                    buffer.append(extra)
                index += len(dollar_tag) - 1
                state = "normal"
                dollar_tag = None
        elif char == "-" and next_char == "-":
            buffer.append(next_char)
            index += 1
            state = "line_comment"
        elif char == "/" and next_char == "*":
            buffer.append(next_char)
            index += 1
            state = "block_comment"
        elif char == "'":
            previous = sql[index - 1] if index else ""
            escape_string = previous in {"e", "E"}
            state = "single_quote"
        elif char == '"':
            state = "double_quote"
        elif char == "$":
            dollar_tag = _dollar_tag_at(sql, index)
            if dollar_tag:
                for extra in dollar_tag[1:]:
                    buffer.append(extra)
                index += len(dollar_tag) - 1
                state = "dollar_quote"
        elif char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []

        index += 1

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
        if state == "line_comment":
            if char == "\n":
                output.append(char)
                state = "normal"
        elif state == "block_comment":
            if char == "\n":
                output.append(char)
            elif char == "*" and next_char == "/":
                index += 1
                state = "normal"
        elif state == "single_quote":
            output.append(char)
            if char == "\\" and escape_string and next_char:
                output.append(next_char)
                index += 1
            elif char == "'":
                if next_char == "'":
                    output.append(next_char)
                    index += 1
                else:
                    state = "normal"
        elif state == "double_quote":
            output.append(char)
            if char == '"':
                if next_char == '"':
                    output.append(next_char)
                    index += 1
                else:
                    state = "normal"
        elif state == "dollar_quote":
            if dollar_tag and sql.startswith(dollar_tag, index):
                output.append(dollar_tag)
                index += len(dollar_tag) - 1
                dollar_tag = None
                state = "normal"
            else:
                output.append(char)
        elif char == "-" and next_char == "-":
            index += 1
            state = "line_comment"
        elif char == "/" and next_char == "*":
            index += 1
            state = "block_comment"
        elif char == "'":
            output.append(char)
            previous = sql[index - 1] if index else ""
            escape_string = previous in {"e", "E"}
            state = "single_quote"
        elif char == '"':
            output.append(char)
            state = "double_quote"
        elif char == "$":
            dollar_tag = _dollar_tag_at(sql, index)
            if dollar_tag:
                output.append(dollar_tag)
                index += len(dollar_tag) - 1
                state = "dollar_quote"
            else:
                output.append(char)
        else:
            output.append(char)
        index += 1
    if state in {"single_quote", "double_quote", "block_comment", "dollar_quote"}:
        raise ValueError("SQL inválido ou truncado: literal/comentário não foi fechado")
    return "".join(output)


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
    match = re.match(
        r"(?is)^INSERT\s+INTO\s+(?:(\"(?:\"\"|[^\"])+\"|[A-Za-z_][\w$]*)\s*\.\s*)?"
        r"(\"(?:\"\"|[^\"])+\"|[A-Za-z_][\w$]*)",
        statement,
    )
    if not match:
        raise ValueError("Não foi possível identificar a tabela de um INSERT")
    schema = _unquote_identifier(match.group(1)) if match.group(1) else None
    return schema, _unquote_identifier(match.group(2))


def prepare_data_statements(sql_content: str) -> tuple[list[str], set[str]]:
    filtered_lines = [
        line
        for line in sql_content.splitlines()
        if not line.lstrip().startswith((r"\restrict", r"\unrestrict"))
    ]
    cleaned_sql = "\n".join(filtered_lines)
    if re.search(r"(?m)^\s*\\", cleaned_sql):
        raise ValueError("Comando interno do psql não suportado no dump")

    prepared: list[str] = []
    insert_tables: set[str] = set()
    for raw_statement in split_sql_statements(cleaned_sql):
        statement = _without_leading_comments(raw_statement)
        if not statement:
            continue
        first_match = re.match(r"(?i)^([A-Z]+)", statement)
        if not first_match:
            raise ValueError(f"Comando SQL não reconhecido: {statement[:80]!r}")
        keyword = first_match.group(1).upper()

        if keyword in TRANSACTION_KEYWORDS or (
            keyword == "START" and re.match(r"(?is)^START\s+TRANSACTION\b", statement)
        ):
            continue
        if keyword == "INSERT":
            schema, table = _insert_target(statement)
            if schema not in (None, "public"):
                raise ValueError(f"INSERT fora do schema public não é permitido: {schema}.{table}")
            if table == "alembic_version":
                continue
            insert_tables.add(table)
            prepared.append(statement)
            continue
        if keyword == "SELECT":
            if re.match(r"(?is)^SELECT\s+(?:pg_catalog\.)?set_config\s*\(", statement):
                continue
            if not re.match(r"(?is)^SELECT\s+(?:pg_catalog\.)?setval\s*\(", statement):
                raise ValueError(f"SELECT não permitido em dump de dados: {statement[:100]!r}")
            prepared.append(statement)
            continue
        if keyword == "SET":
            setting_match = re.match(r"(?is)^SET\s+(?:SESSION\s+|LOCAL\s+)?([A-Za-z_]+)", statement)
            setting = setting_match.group(1).lower() if setting_match else ""
            if setting not in ALLOWED_SET_NAMES:
                raise ValueError(f"SET não permitido em dump de dados: {setting or statement[:80]}")
            if setting in {"search_path", "client_encoding", "standard_conforming_strings"}:
                continue
            prepared.append(statement)
            continue
        raise ValueError(
            f"Dump deve conter somente INSERT/SET/setval; comando {keyword} não é permitido"
        )

    if not prepared:
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
    if dump_revisions and dump_revisions != revisions:
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


def _read_sql_file(sql_path: Path) -> str:
    if not sql_path.is_file():
        raise FileNotFoundError(f"Arquivo SQL não encontrado: {sql_path}")
    if sql_path.stat().st_size > MAX_SQL_BYTES:
        raise ValueError(f"Arquivo SQL excede o limite de {MAX_SQL_BYTES} bytes")
    return sql_path.read_text(encoding="utf-8")


def apply_sql_content(
    sql_content: str,
    *,
    truncate_first: bool = True,
    allow_destructive: bool = False,
    expected_database: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    dump_revisions = extract_dump_alembic_revisions(sql_content)
    statements, insert_tables = prepare_data_statements(sql_content)
    if truncate_first and not allow_destructive and not dry_run:
        raise RuntimeError("Restauração destrutiva não confirmada; use --yes")

    creds = get_pg_credentials()
    connection = connect_with_retry(creds)
    connection.autocommit = False
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT current_database()")
        current_database = cursor.fetchone()[0]
        if expected_database and current_database != expected_database:
            raise RuntimeError(
                f"Banco conectado é {current_database!r}, mas {expected_database!r} foi confirmado"
            )
        application_tables, target_revisions = _validate_target_schema(
            cursor,
            insert_tables,
            dump_revisions,
        )
        if dry_run:
            connection.rollback()
            return {
                "database": current_database,
                "statements": len(statements),
                "insert_tables": sorted(insert_tables),
                "alembic_revisions": sorted(target_revisions),
                "truncated_tables": [],
            }

        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('spe:data_restore'))")
        cursor.execute("SET LOCAL search_path = public, pg_catalog")
        cursor.execute("SET LOCAL standard_conforming_strings = on")
        if truncate_first:
            _truncate_database_tables(cursor, application_tables)
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")
        for statement in statements:
            cursor.execute(statement)
        connection.commit()
        return {
            "database": current_database,
            "statements": len(statements),
            "insert_tables": sorted(insert_tables),
            "alembic_revisions": sorted(target_revisions),
            "truncated_tables": application_tables if truncate_first else [],
        }
    except Exception as exc:
        connection.rollback()
        raise RuntimeError(f"Falha ao aplicar SQL no PostgreSQL: {exc}") from exc
    finally:
        cursor.close()
        connection.close()


def apply_sql_file(
    sql_path: Path,
    truncate_first: bool = True,
    *,
    allow_destructive: bool = False,
    expected_database: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    return apply_sql_content(
        _read_sql_file(sql_path),
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
        ROOT_DIR / "spe.zip",
        ROOT_DIR / "scripts" / "spe.zip",
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
) -> dict[str, Any]:
    target = source_path or find_backup_source()
    if not target or not target.is_file():
        raise FileNotFoundError("Arquivo de backup ou dump não encontrado")

    if target.suffix.lower() != ".zip":
        return apply_sql_file(
            target,
            allow_destructive=allow_destructive,
            expected_database=expected_database,
            dry_run=dry_run,
        )

    with zipfile.ZipFile(target, "r") as archive:
        member = _find_data_member(archive)
        if member.file_size > MAX_SQL_BYTES:
            raise ValueError(f"SQL compactado excede o limite de {MAX_SQL_BYTES} bytes")
        sql_content = archive.read(member).decode("utf-8")
    return apply_sql_content(
        sql_content,
        allow_destructive=allow_destructive,
        expected_database=expected_database,
        dry_run=dry_run,
    )


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
            )
        else:
            result = apply_sql_file(
                args.file,
                truncate_first=not args.no_truncate,
                allow_destructive=args.yes,
                expected_database=args.confirm_database,
                dry_run=args.dry_run,
            )
        action = "validado" if args.dry_run else "aplicado"
        print(
            f"Dump {action} com sucesso em {result['database']}: "
            f"{result['statements']} comandos, {len(result['insert_tables'])} tabelas com dados."
        )
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
