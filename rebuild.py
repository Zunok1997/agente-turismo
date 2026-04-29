"""
Lee draft.txt, construye el HTML y abre el preview. No llama a la API.
Uso: python rebuild.py
"""
import os
from pathlib import Path
from datetime import datetime

from main import build_html

draft = Path(__file__).parent / "draft.txt"
if not draft.exists():
    raise SystemExit("ERROR: draft.txt no encontrado. Corré preview.py primero.")

text  = draft.read_text(encoding="utf-8")
today = datetime.now().strftime("%d de %B de %Y")

print("Construyendo HTML desde draft.txt...")
html = build_html(text, today)

output = Path(__file__).parent / "preview.html"
output.write_text(html, encoding="utf-8")
print(f"Listo. Abriendo preview...")

try:
    os.startfile(str(output))
except AttributeError:
    import webbrowser
    webbrowser.open(output.as_uri())
