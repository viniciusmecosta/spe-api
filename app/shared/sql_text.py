import os
import re
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path


class SqlLineScanner:
    def __init__(self):
        self.state = 'normal'
        self.tag = ''
        self.escape = False
        self.depth = 0

    def block(self, line: str, index: int) -> int:
        pair = line[index:index + 2]
        if pair == '/*':
            self.depth += 1
            return index + 2
        if pair == '*/':
            self.depth -= 1
            if not self.depth:
                self.state = 'normal'
            return index + 2
        return index + 1

    def dollar(self, line: str, index: int) -> int:
        if line.startswith(self.tag, index):
            self.state = 'normal'
            return index + len(self.tag)
        return index + 1

    def quoted(self, line: str, index: int) -> int:
        quote = "'" if self.state == 'single' else '"'
        if self.state == 'single' and self.escape and line[index] == '\\':
            return index + 2
        if line[index] == quote:
            if line[index:index + 2] == quote * 2:
                return index + 2
            self.state = 'normal'
        return index + 1

    @staticmethod
    def escape_string(line: str, index: int) -> bool:
        return index > 0 and line[index - 1] in 'eE' and (
                index < 2 or not (line[index - 2].isalnum() or line[index - 2] == '_'))

    def normal(self, line: str, index: int) -> int | None:
        char, pair = line[index], line[index:index + 2]
        if pair == '--':
            return None
        if pair == '/*':
            self.state, self.depth = 'block', 1
            return index + 2
        if char == "'":
            self.state, self.escape = 'single', self.escape_string(line, index)
        elif char == '"':
            self.state = 'double'
        elif char == '$':
            match = re.match(r"\$(?:[^\W\d]\w*)?\$", line[index:])
            if match:
                self.tag, self.state = match.group(), 'dollar'
                return index + len(self.tag)
        return index + 1

    def consume(self, line: str) -> None:
        index = 0
        while index < len(line):
            if self.state == 'block':
                index = self.block(line, index)
            elif self.state == 'dollar':
                index = self.dollar(line, index)
            elif self.state in ('single', 'double'):
                index = self.quoted(line, index)
            else:
                next_index = self.normal(line, index)
                if next_index is None:
                    return
                index = next_index


def sql_lines(lines: Iterable[str], *, reject_psql_commands: bool = False) -> Iterator[str]:
    scanner = SqlLineScanner()
    for line in lines:
        stripped = line.lstrip()
        if scanner.state == 'normal' and stripped.startswith('\\'):
            if re.match(r"^\\(?:un)?restrict(?:\s|$)", stripped):
                continue
            if reject_psql_commands:
                raise ValueError('Comando interno do psql não suportado no dump')
        scanner.consume(line)
        yield line


def remove_psql_directives(path: Path) -> None:
    with tempfile.NamedTemporaryFile(prefix=f'.{path.name}.', suffix='.clean.tmp', dir=path.parent,
                                     delete=False) as temporary:
        target = Path(temporary.name)
    try:
        with (
            target.open("wb") as output,
            path.open("r", encoding="utf-8", newline="") as source,
        ):
            for line in sql_lines(source):
                output.write(line.encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        target.replace(path)
    finally:
        target.unlink(missing_ok=True)
