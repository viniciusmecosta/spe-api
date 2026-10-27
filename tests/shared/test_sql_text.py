import pytest

from app.shared.sql_text import remove_psql_directives, sql_lines
from scripts.apply_sql_to_postgresql import prepare_data_statements


@pytest.mark.parametrize(
    "value",
    [
        "first\n\\network-path\nlast",
        "first\n\\restrict user content\nlast",
        "first\n\\unrestrict user content\nlast",
        "with ''; quotes\n\\path\nlast",
    ],
)
def test_directive_filter_preserves_multiline_values(tmp_path, value):
    sql = f"INSERT INTO companies(name) VALUES ('{value}');\n"
    dump = tmp_path / "data.sql"
    dump.write_text("\\restrict token\n" + sql + "\\unrestrict token\n")
    remove_psql_directives(dump)
    assert dump.read_text() == sql
    statements, tables = prepare_data_statements(dump.read_text())
    assert tables == {"companies"}
    assert statements == [sql.strip()]


def test_directive_filter_preserves_dollar_quotes_and_comments():
    sql = "SELECT $value$\n\\restrict literal\n$value$;\n/* nested /* comment */\n\\restrict comment\n*/\n"
    assert "".join(sql_lines(sql.splitlines(keepends=True))) == sql


def test_real_psql_commands_are_rejected():
    with pytest.raises(ValueError, match="psql"):
        prepare_data_statements(
            "\\connect another_database\nINSERT INTO users(id) VALUES (1);"
        )


def test_sql_line_scanner_escaped_quote_and_double_quotes():
    from app.shared.sql_text import SqlLineScanner

    scanner = SqlLineScanner()
    scanner.consume(r"""SELECT E'abc\'def', "col_name" FROM t;""")
    assert scanner.state == "normal"
