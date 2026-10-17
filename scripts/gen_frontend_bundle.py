#!/usr/bin/env python3
"""Régénère web_frontend_bundle_data.py à partir de dist/ (après `npm run build`).

Usage : python scripts/gen_frontend_bundle.py
Format identique à l'existant : { '/chemin': 'contenu en base64' }.
"""
import base64
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
OUT = ROOT / "web_frontend_bundle_data.py"

if not (DIST / "index.html").exists():
    raise SystemExit("dist/index.html introuvable : lancez d'abord `npm run build`.")

lines = ["# Auto-generated embedded frontend bundle", "EMBEDDED_FRONTEND = {"]
for f in sorted(p for p in DIST.rglob("*") if p.is_file()):
    key = "/" + f.relative_to(DIST).as_posix()
    lines.append(f"    {key!r}: {base64.b64encode(f.read_bytes()).decode('ascii')!r},")
lines.append("}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{OUT.name} régénéré : {len(lines) - 3} fichiers")
