import os
import re
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path


def sql_lines(
    lines: Iterable[str], *, reject_psql_commands: bool = False
) -> Iterator[str]:
    state, tag, escape, depth = "normal", "", False, 0
    for line in lines:
        stripped = line.lstrip()
        if state == "normal" and stripped.startswith("\\"):
            if re.match(r"^\\(?:un)?restrict(?:\s|$)", stripped):
                continue
            if reject_psql_commands:
                raise ValueError("Comando interno do psql não suportado no dump")
        index = 0
        while index < len(line):
            char, pair = line[index], line[index : index + 2]
            if state == "block":
                if pair == "/*":
                    depth += 1
                    index += 2
                    continue
                if pair == "*/":
                    depth -= 1
                    if not depth:
                        state = "normal"
                    index += 2
                    continue
            elif state == "dollar":
                if line.startswith(tag, index):
                    index += len(tag)
                    state = "normal"
                    continue
            elif state in {"single", "double"}:
                quote = "'" if state == "single" else '"'
                if state == "single" and escape and char == "\\":
                    index += 2
                    continue
                if char == quote:
                    if pair == quote * 2:
                        index += 2
                        continue
                    state = "normal"
            elif pair == "--":
                break
            elif pair == "/*":
                state, depth = "block", 1
                index += 2
                continue
            elif char == "'":
                state = "single"
                escape = (
                    index > 0
                    and line[index - 1] in "eE"
                    and (
                        index < 2
                        or not (line[index - 2].isalnum() or line[index - 2] == "_")
                    )
                )
            elif char == '"':
                state = "double"
            elif char == "$":
                match = re.match(r"\$(?:[^\W\d]\w*)?\$", line[index:])
                if match:
                    tag, state = match.group(), "dollar"
                    index += len(tag)
                    continue
            index += 1
        yield line


def remove_psql_directives(path: Path) -> None:
    temporary = tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.",
        suffix=".clean.tmp",
        dir=path.parent,
        delete=False,
    )
    target = Path(temporary.name)
    try:
        with (
            temporary as output,
            path.open("r", encoding="utf-8", newline="") as source,
        ):
            for line in sql_lines(source):
                output.write(line.encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        target.replace(path)
    finally:
        target.unlink(missing_ok=True)
