"""
Genera el newsletter y lo abre en el browser. No envía mail.
Uso: python preview.py
"""
import os
import webbrowser
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

if not os.environ.get("GROQ_API_KEY"):
    raise SystemExit("ERROR: GROQ_API_KEY no está configurada. Revisá tu archivo .env")

from main import fetch_news, generate_newsletter, build_html

today = datetime.now().strftime("%d de %B de %Y")

print("Buscando noticias...")
articles = fetch_news(days_back=7)
small_ship = [a for a in articles if a["small_ship"]]
print(f"  {len(articles)} artículos ({len(small_ship)} cruceros ≤100 pax)")

print("Generando análisis con IA...")
text = generate_newsletter(articles)

print("Construyendo HTML...")
html = build_html(text, today)

output = Path(__file__).parent / "preview.html"
output.write_text(html, encoding="utf-8")

print(f"Guardado en {output}")
print("Abriendo en el browser...")
try:
    os.startfile(str(output))  # Windows
except AttributeError:
    webbrowser.open(output.as_uri())
