from __future__ import annotations

from pathlib import Path


PUBLIC_DEMO_FORBIDDEN = [
    "C:" + "\\",
    "C:/Us" + "ers",
    "/Us" + "ers/",
    "/ho" + "me/",
    "Chef" + "McSexy",
    "WS" + "mith",
    "api" + "_key",
    "api" + "key",
    "." + "env",
    "." + "sqlite",
    "." + "sqlite3",
    "." + "db",
    "real " + "customer",
    "real " + "client",
]


def test_public_demo_does_not_expose_private_values() -> None:
    docs_dir = Path("docs")
    scanned = []
    for path in docs_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".html", ".css", ".js", ".md"}:
            text = path.read_text(encoding="utf-8")
            scanned.append(path)
            for forbidden in PUBLIC_DEMO_FORBIDDEN:
                assert forbidden.lower() not in text.lower(), f"{forbidden} found in {path}"

    assert scanned
