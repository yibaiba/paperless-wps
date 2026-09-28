"""Split long cell text into continuation rows without duplicating procurement quantities."""

from math import ceil
from unicodedata import east_asian_width

from openpyxl.utils import get_column_letter

LINE_HEIGHT = 15
LINES_PER_DETAIL_ROW = 24
CELL_PADDING = 2


def wrapped_lines(text, width):
    lines, current, used = [], "", 0
    for character in text:
        size = 2 if east_asian_width(character) in ("W", "F") else 1
        if character == "\n":
            lines.append(current + "\n")
            current, used = "", 0
            continue
        if current and used + size > width:
            lines.append(current)
            current, used = "", 0
        current += character
        used += size
    return lines + [current]


def detail_rows(ws, lines):
    result = []
    for line in lines:
        texts = detail_text(line)
        wrapped = {
            column: wrapped_lines(
                text, max(1, ws.column_dimensions[get_column_letter(column)].width - CELL_PADDING)
            )
            for column, text in texts.items()
        }
        count = max(ceil(len(parts) / LINES_PER_DETAIL_ROW) for parts in wrapped.values())
        for index in range(count):
            start = index * LINES_PER_DETAIL_ROW
            fragments = {
                c: parts[start : start + LINES_PER_DETAIL_ROW] for c, parts in wrapped.items()
            }
            result.append(
                dict(
                    line=line,
                    continuation=index > 0,
                    texts={c: "".join(parts) for c, parts in fragments.items()},
                    height=max(28, max(map(len, fragments.values())) * LINE_HEIGHT),
                )
            )
    return result


def detail_text(line):
    notes = [line["note"], *line["issues"]]
    names = sorted({c["system_name"] for c in line["consumers"]})
    if names:
        notes.append("服务：" + " / ".join(names))
    return {
        2: line["name"],
        3: line["model"],
        4: line["specification"],
        6: line["unit"],
        9: line["brand"],
        10: "；".join(n for n in notes if n),
    }
