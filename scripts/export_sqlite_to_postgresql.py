import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = ROOT_DIR / "spe.db"
DEFAULT_OUTPUT_SQL_PATH = ROOT_DIR / "scripts" / "data_inserts_postgresql.sql"


def get_timezone() -> str:
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TIMEZONE="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.getenv("TIMEZONE", "America/Fortaleza")


TABLE_ORDER = [
    "alembic_version",
    "companies",
    "printers",
    "users",
    "device_credentials",
    "firmwares",
    "holidays",
    "user_biometrics",
    "user_work_schedule_configs",
    "time_records",
    "adjustment_requests",
    "adjustment_attachments",
    "payroll_closures",
    "audit_logs",
    "routine_logs",
]

BOOLEAN_COLUMNS = {
    "companies": {"auto_print_receipt"},
    "printers": {"status"},
    "users": {
        "is_active",
        "can_manual_punch_desktop",
        "can_manual_punch_mobile",
        "can_export_report",
        "is_exempt_from_rules",
        "is_tolerance_exempt",
        "auto_print_receipt",
    },
    "device_credentials": {"is_active"},
    "user_work_schedule_configs": {"is_daily_excess_enabled"},
    "time_records": {"is_ignored", "is_verified"},
    "payroll_closures": {"is_closed"},
}

JSONB_COLUMNS = {
    "audit_logs": {"old_data", "new_data"},
}

IDENTITY_TABLES = [
    "companies",
    "printers",
    "users",
    "device_credentials",
    "firmwares",
    "holidays",
    "user_biometrics",
    "user_work_schedule_configs",
    "time_records",
    "adjustment_requests",
    "adjustment_attachments",
    "payroll_closures",
    "audit_logs",
    "routine_logs",
]


def format_cell(table_name: str, col_name: str, val: object) -> str:
    if val is None:
        return "NULL"

    if col_name in BOOLEAN_COLUMNS.get(table_name, set()):
        val_str = str(val).strip().lower()
        if val_str in ("1", "true", "t"):
            return "TRUE"
        if val_str in ("0", "false", "f"):
            return "FALSE"
        return "NULL"

    if col_name in JSONB_COLUMNS.get(table_name, set()):
        if isinstance(val, dict):
            val_str = json.dumps(val, ensure_ascii=False)
        else:
            val_str = str(val)
        escaped = val_str.replace("'", "''")
        return f"'{escaped}'::jsonb"

    if isinstance(val, (int, float)):
        return str(val)

    val_str = str(val)
    if "\n" in val_str or "\r" in val_str:
        escaped = (
            val_str.replace("\\", "\\\\")
            .replace("'", "''")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
        return f"E'{escaped}'"

    val_str = val_str.replace("'", "''")
    return f"'{val_str}'"


def export_sqlite_to_postgresql(
        sqlite_path: Path, output_sql_path: Path, batch_size: int = 100
) -> dict[str, int]:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"Arquivo SQLite não encontrado: {sqlite_path}")

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    stats: dict[str, int] = {}
    tz = get_timezone()

    with open(output_sql_path, "w", encoding="utf-8") as out:
        out.write("BEGIN;\n\n")
        out.write("SET client_encoding = 'UTF8';\n")
        out.write("SET standard_conforming_strings = on;\n")
        out.write("SET check_function_bodies = false;\n")
        out.write("SET client_min_messages = warning;\n")
        out.write(f"SET timezone = '{tz}';\n\n")

        for table_name in TABLE_ORDER:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            if not cursor.fetchone():
                stats[table_name] = 0
                continue

            order_clause = " ORDER BY id ASC" if table_name != "alembic_version" else ""
            cursor.execute(f"SELECT * FROM {table_name}{order_clause}")
            rows = cursor.fetchall()
            stats[table_name] = len(rows)

            if not rows:
                continue

            cols = list(rows[0].keys())
            cols_str = ", ".join(f'"{c}"' for c in cols)

            if table_name == "alembic_version":
                for r in rows:
                    v = format_cell(table_name, "version_num", r["version_num"])
                    out.write(
                        f"INSERT INTO alembic_version (version_num) VALUES ({v}) ON CONFLICT (version_num) DO NOTHING;\n"
                    )
                out.write("\n")
                continue

            for i in range(0, len(rows), batch_size):
                batch = rows[i: i + batch_size]
                value_tuples = []
                for row in batch:
                    formatted_vals = [
                        format_cell(table_name, c, row[c]) for c in cols
                    ]
                    value_tuples.append("(" + ", ".join(formatted_vals) + ")")

                values_str = ",\n  ".join(value_tuples)
                out.write(
                    f"INSERT INTO {table_name} ({cols_str}) VALUES\n  {values_str};\n"
                )
            out.write("\n")

        for table_name in IDENTITY_TABLES:
            out.write(
                f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE((SELECT MAX(id) FROM {table_name}), 1));\n"
            )

        out.write("\nCOMMIT;\n")

    conn.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporta dados do SQLite (spe.db) para script SQL compatível com PostgreSQL."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help="Caminho do arquivo SQLite (padrão: spe.db na raiz)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT_SQL_PATH,
        help="Caminho do script SQL de saída (padrão: scripts/data_inserts_postgresql.sql)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Tamanho do lote para comandos INSERT em lote (padrão: 100)",
    )

    args = parser.parse_args()

    try:
        stats = export_sqlite_to_postgresql(args.db, args.out, args.batch_size)
        print(f"Sucesso! Script gerado em: {args.out}")
        print("\nResumo de registros exportados:")
        for table, count in stats.items():
            print(f"  - {table}: {count} linhas")
    except Exception as e:
        print(f"Erro na exportação: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
