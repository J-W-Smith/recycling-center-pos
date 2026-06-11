from __future__ import annotations

from pathlib import Path


def write_text_pdf(text: str, output_path: str | Path, *, title: str = "Report") -> Path:
    """Write a simple single-font PDF without external dependencies."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = _wrap_lines(text.splitlines() or [""], width=92)
    content = ["BT", "/F1 9 Tf", "36 760 Td", "12 TL"]
    for index, line in enumerate(lines):
        if index:
            content.append("T*")
        content.append(f"({_escape_pdf_text(line)}) Tj")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        (
            b"<< /Title (" + _escape_pdf_text(title).encode("latin-1", errors="replace") + b") "
            b"/Producer (recycling-center-pos) >>"
        ),
    ]

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 6 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(output)
    return path


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_lines(lines: list[str], *, width: int) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        if len(line) <= width:
            wrapped.append(line)
            continue
        remaining = line
        while len(remaining) > width:
            wrapped.append(remaining[:width])
            remaining = remaining[width:]
        wrapped.append(remaining)
    return wrapped
