#!/usr/bin/env python3
"""
Baut docs/index.html aus data/dashboard.json.
Das HTML ist standalone — keine externen Requests, kein Build-Schritt.
Oeffne es lokal im Browser oder aktiviere GitHub Pages auf /docs.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "dashboard.json"
OUT = ROOT / "docs" / "index.html"

TEMPLATE = Path(__file__).resolve().parent / "template.html"


def main():
    data = json.loads(DATA.read_text())
    html = TEMPLATE.read_text()
    html = html.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print(f"[build] {OUT} geschrieben")


if __name__ == "__main__":
    main()
