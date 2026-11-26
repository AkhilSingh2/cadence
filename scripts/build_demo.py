#!/usr/bin/env python3
"""Build the static demo of the web UI into _site/ for GitHub Pages.

Copies backend/web as-is and adds demo/demo-api.js, which answers the UI's API
calls in the browser with sample data. The FastAPI app never serves this file.
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"

shutil.rmtree(OUT, ignore_errors=True)
shutil.copytree(ROOT / "backend" / "web", OUT)
shutil.copy2(ROOT / "demo" / "demo-api.js", OUT / "demo-api.js")

index = OUT / "index.html"
html = index.read_text(encoding="utf-8")
marker = '<script src="./app.js"></script>'
if marker not in html:
    raise SystemExit("index.html no longer loads ./app.js; update build_demo.py")
html = html.replace(marker, '<script src="./demo-api.js"></script>\n  ' + marker)
html = html.replace("<title>Trainer</title>", "<title>Trainer — demo</title>")
index.write_text(html, encoding="utf-8")
(OUT / ".nojekyll").write_text("")
print(f"demo built -> {OUT.relative_to(ROOT)}")
