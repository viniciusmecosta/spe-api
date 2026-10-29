import pytest

from app.shared.sql_text import remove_psql_directives, sql_lines


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


def test_directive_filter_preserves_dollar_quotes_and_comments():
    sql = "SELECT $value$\n\\restrict literal\n$value$;\n/* nested /* comment */\n\\restrict comment\n*/\n"
    assert "".join(sql_lines(sql.splitlines(keepends=True))) == sql




def test_sql_line_scanner_escaped_quote_and_double_quotes():
    from app.shared.sql_text import SqlLineScanner

    scanner = SqlLineScanner()
    scanner.consume(r"""SELECT E'abc\'def', "col_name" FROM t;""")
    assert scanner.state == "normal"
