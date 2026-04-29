import os
import re
import smtplib
import feedparser
import anthropic
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Fuentes RSS
# ---------------------------------------------------------------------------
RSS_FEEDS = [
    {"name": "Skift",                              "url": "https://skift.com/feed/"},
    {"name": "Adventure Travel Trade Association", "url": "https://www.adventuretravel.biz/feed/"},
    {"name": "Condé Nast Traveler",                "url": "https://www.cntraveler.com/feed/rss"},
    {"name": "Condé Nast Traveller UK",           "url": "https://www.cntraveller.com/feed/rss"},
    {"name": "Travel + Leisure",                   "url": "https://www.travelandleisure.com/rss"},
    {"name": "Robb Report Travel",                 "url": "https://robbreport.com/travel/feed/"},
    {"name": "National Geographic Travel",         "url": "https://www.nationalgeographic.com/travel/rss"},
    {"name": "Luxury Travel Magazine",             "url": "https://www.luxurytravelmagazine.com/rss/news.xml"},
    {"name": "Safari Bookings News",               "url": "https://www.safaribookings.com/blog/feed"},
    {"name": "Seatrade Cruise News",               "url": "https://www.seatrade-cruise.com/rss.xml"},
    {"name": "Cruise Industry News",               "url": "https://www.cruiseindustrynews.com/cruise-news/feed/"},
    {"name": "The Expedition Cruise Network",      "url": "https://expeditioncruisenetwork.com/feed/"},
    {"name": "WTTC",                               "url": "https://wttc.org/feed/"},
]

KEYWORDS = [
    "luxury", "lujo", "safari", "patagonia", "antarctica", "antarctic", "arctic",
    "ártico", "antártica", "costa rica", "guanacaste", "africa", "áfrica",
    "ecotourism", "ecoturismo", "adventure", "aventura", "sustainable tourism",
    "turismo sostenible", "high-end", "boutique hotel", "lodge", "expedition",
    "wilderness", "remote", "wildlife", "cruise", "yacht", "glamping",
    "conservation", "conservación", "nature", "naturaleza",
    "expedition cruise", "small ship", "small-ship", "boutique cruise",
    "hurtigruten", "silversea", "ponant", "lindblad", "aurora expeditions",
    "quark expeditions", "hapag-lloyd", "viking expeditions", "scenic eclipse",
    "coral expeditions", "aqua expeditions",
    "investment", "inversión", "funding", "concession", "concessión",
    "permit", "permiso", "regulation", "regulación", "conservation policy",
    "visa", "access", "acceso", "protected area", "área protegida",
    "new lodge", "new hotel", "opening", "apertura", "development", "desarrollo",
]

SMALL_SHIP_OPERATORS = {
    "hurtigruten", "silversea", "ponant", "lindblad", "aurora expeditions",
    "quark expeditions", "hapag-lloyd", "viking", "scenic eclipse",
    "coral expeditions", "aqua expeditions", "national geographic",
    "polar latitudes", "one ocean", "g adventures", "intrepid",
}


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
def _is_small_ship_cruise(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    small_capacity_phrases = [
        "small ship", "small-ship", "boutique cruise", "expedition ship",
        "expedition cruise", "intimate ship", "luxury expedition",
        "100 passenger", "100-passenger", "fewer than 100",
        "under 100 passengers", "100 guests",
    ]
    if any(p in text for p in small_capacity_phrases):
        return True
    if any(op in text for op in SMALL_SHIP_OPERATORS):
        return True
    return False


def _extract_image(entry) -> str:
    if hasattr(entry, "media_content") and entry.get("media_content"):
        url = entry.media_content[0].get("url", "")
        if url:
            return url
    if hasattr(entry, "media_thumbnail") and entry.get("media_thumbnail"):
        url = entry.media_thumbnail[0].get("url", "")
        if url:
            return url
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image/"):
                return enc.get("url", "")
    return ""


def fetch_news(days_back: int = 7) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=days_back)
    articles = []
    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            count = 0
            for entry in feed.entries[:40]:
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6])
                if pub_date and pub_date < cutoff:
                    continue
                title   = entry.get("title", "")
                summary = entry.get("summary", "")
                text    = (title + " " + summary).lower()
                if not any(kw in text for kw in KEYWORDS):
                    continue
                articles.append({
                    "source":     feed_info["name"],
                    "title":      title,
                    "summary":    summary[:700],
                    "link":       entry.get("link", ""),
                    "date":       pub_date.strftime("%Y-%m-%d") if pub_date else "fecha desconocida",
                    "small_ship": _is_small_ship_cruise(title, summary),
                    "image":      _extract_image(entry),
                })
                count += 1
            print(f"  [{feed_info['name']}] {count} artículos relevantes")
        except Exception as e:
            print(f"  [warn] {feed_info['name']}: {e}")
    return articles


def _format_articles(articles: list[dict], small_ship_only: bool = False) -> str:
    subset = [a for a in articles if not small_ship_only or a["small_ship"]]
    if not subset:
        return "(No articles in this category this week.)"
    lines = []
    for a in subset:
        block = (
            f"[{a['source']}] {a['date']} {'⚑ SMALL SHIP ≤100 PAX' if a['small_ship'] else ''}\n"
            f"Title: {a['title']}\n"
            f"Summary: {a['summary']}\n"
            f"URL: {a['link']}"
        )
        if a.get("image"):
            block += f"\nIMAGE: {a['image']}"
        lines.append(block)
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Generación con LLM
# ---------------------------------------------------------------------------
def generate_newsletter(articles: list[dict]) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY no está configurada. Revisá tu archivo .env")

    client     = anthropic.Anthropic(api_key=api_key)
    today      = datetime.now().strftime("%d de %B de %Y")
    small_ship = [a for a in articles if a["small_ship"]]

    prompt = f"""You are a senior analyst specializing in high-end tourism, adventure travel, ecotourism, and tourism project evaluation.
Your task is to generate a weekly professional newsletter in the style of a strategic consulting report.
The reader is a tourism project analyst focused on luxury and adventure travel.

Today: {today}
Period covered: last 7 days

=== ALL ARTICLES THIS WEEK ===
{_format_articles(articles)}

=== SMALL SHIP CRUISE ARTICLES ≤100 PASSENGERS (HIGH PRIORITY) ===
{_format_articles(articles, small_ship_only=True)}

ABSOLUTE RULES — NON-NEGOTIABLE:
1. LANGUAGE PER ARTICLE: Detect the language of each source article. Write the ENTIRE analysis of that article in the SAME language as the source. English source → English. Spanish source → Spanish. NEVER mix within a single news block.
2. NO UNSOURCED CLAIMS: Every factual claim MUST reference a specific article. If you cannot back it up, do not state it.
3. ALWAYS INCLUDE URL: After each news item, add a line: URL: [full link from the article]
4. IMAGE LINE: If the article data includes an IMAGE: field, echo it as: IMAGE: [url] — place it right after the SOURCE line.
5. NO DATA INVENTION: Do not invent operators, projects, numbers, or events not present in the articles.
6. HONEST GAPS: If a region has no news this week, say so clearly.
7. SMALL SHIP CRUISES ≤100 PAX: High-priority section. 3–4 sentences of analysis per item.
8. STYLE: Dense, professional, no filler. Consulting report style.
9. EVENTS TABLE: List upcoming industry events for the next 60 days. Mark (confirmed) if from an article, (verify date) if from general knowledge.

NEWS ITEM FORMAT — use this EXACT format for every news item in sections 2, 3, and 4:
TITLE: [original article title]
SOURCE: [source name] | [date]
IMAGE: [url — only if IMAGE field was provided in article data, otherwise omit this line entirely]
ANALYSIS: [analysis in source language]
URL: [full article URL]

Generate the newsletter with EXACTLY this structure:

================================================================================
HIGH-END TOURISM NEWSLETTER
Week of {today}
================================================================================

1. EXECUTIVE SUMMARY
--------------------------------------------------------------------------------
[2–3 paragraphs. Key trends of the week, backed by articles.]

2. TOP NEWS & TRENDS
--------------------------------------------------------------------------------
[Use NEWS ITEM FORMAT above. Max 8 items.]

3. REGIONAL ANALYSIS
--------------------------------------------------------------------------------

3.1 ANTARCTICA / ARCTIC
[Use NEWS ITEM FORMAT. If no news, give seasonal/structural context as a paragraph.]

3.2 PATAGONIA (CHILE & ARGENTINA)
[Same]

3.3 AFRICA — SAFARIS & LUXURY TOURISM
[Same]

3.4 GUANACASTE, COSTA RICA
[Same]

4. EXPEDITION CRUISES — SHIPS ≤100 PASSENGERS
--------------------------------------------------------------------------------
[Use NEWS ITEM FORMAT with 3–4 sentence ANALYSIS. If no articles, give segment context.]

Reference operators: Hurtigruten, Ponant, Silversea Expeditions, Lindblad, Aurora Expeditions, Quark Expeditions, Hapag-Lloyd Expeditions, Scenic Eclipse, Aqua Expeditions.

5. INVESTMENT SIGNALS
--------------------------------------------------------------------------------
[Bullets. New projects, lodge/hotel openings, funding, operator expansions. Source each item.]

6. REGULATORY PULSE
--------------------------------------------------------------------------------
[Bullets. Visa changes, conservation policy, access restrictions, concession news.]

7. RADAR DEL EVALUADOR
--------------------------------------------------------------------------------
[5–6 concrete bullets. What a tourism project evaluator should watch this week.]

8. UPCOMING INDUSTRY EVENTS
--------------------------------------------------------------------------------
| Event | Date | Location | Topic |
|-------|------|----------|-------|
[Upcoming events for the next 60 days.]

9. STRATEGIC CONCLUSION
--------------------------------------------------------------------------------
[1–2 paragraphs. Synthesis and what to monitor next week.]

10. EXPERT'S TAKE
--------------------------------------------------------------------------------
[2–3 paragraphs. Your personal informed opinion as a senior luxury tourism consultant: What do these news collectively signal? Where is high-end tourism heading in the next 12–24 months? What opportunities or risks stand out? Clearly labeled as your assessment, not sourced from articles.]

================================================================================
Generated: {today} | Small ship articles this week: {len(small_ship)}
================================================================================
"""

    print("  Enviando prompt al modelo...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=5000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
def _md_bold(text: str) -> str:
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)


def build_html(text: str, today: str) -> str:
    lines      = text.split("\n")
    parts      = []
    in_list    = False
    in_section = False
    in_table   = False
    in_details = False
    is_cruise  = False

    def close_list():
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    def close_table():
        nonlocal in_table
        if in_table:
            parts.append("</tbody></table>")
            in_table = False

    def close_details():
        nonlocal in_details
        if in_details:
            parts.append("</div></details>")
            in_details = False

    def close_section():
        nonlocal in_section
        if in_section:
            parts.append("</div>")
            in_section = False

    for line in lines:
        s = line.strip()

        # Decoration / metadata lines
        if re.match(r"^[=]{8,}$", s) or re.match(r"^[-]{8,}$", s):
            close_list(); close_table(); close_details()
            continue
        if "HIGH-END TOURISM NEWSLETTER" in s or "NEWSLETTER DE TURISMO" in s:
            continue
        if re.match(r"^Week of ", s) or re.match(r"^Semana del ", s):
            continue
        if re.match(r"^Generated:", s) or re.match(r"^Generado:", s):
            continue

        # Table row
        if s.startswith("|"):
            close_list(); close_details()
            cells = [c.strip() for c in s.split("|")[1:-1]]
            if all(re.match(r"^[-:\s]+$", c) for c in cells):
                continue
            if not in_table:
                parts.append('<table class="event-table"><thead><tr>')
                parts.append("".join(f"<th>{c}</th>" for c in cells))
                parts.append("</tr></thead><tbody>")
                in_table = True
            else:
                parts.append("<tr>")
                parts.append("".join(f"<td>{c}</td>" for c in cells))
                parts.append("</tr>")
            continue
        else:
            close_table()

        # Main section header  "1. EXECUTIVE SUMMARY"
        m = re.match(r"^(\d+)\.\s+(.+)$", s)
        if m and s == s.upper():
            close_list(); close_details(); close_section()
            num   = int(m.group(1))
            title = m.group(2).strip()
            is_cruise = num == 4
            is_expert = num == 10
            if is_cruise:
                cls = "section cruise-section"
            elif is_expert:
                cls = "section expert-section"
            else:
                cls = "section"
            parts.append(f'<div class="{cls}">')
            parts.append(f'<h2 class="section-title">{num}. {title}</h2>')
            in_section = True
            continue

        # Subsection header  "3.1 ANTARCTICA / ARCTIC"
        m2 = re.match(r"^(\d+\.\d+)\s+(.+)$", s)
        if m2:
            close_list(); close_details()
            parts.append(f'<h3 class="sub-title">{m2.group(1)} {m2.group(2)}</h3>')
            continue

        # ── News item structured format ──────────────────────────────────────

        # TITLE: → open collapsible item
        m_title = re.match(r"^TITLE:\s*(.+)$", s)
        if m_title:
            close_list(); close_details()
            title_text = _md_bold(m_title.group(1))
            cruise_cls = " cruise-item" if is_cruise else ""
            parts.append(f'<details class="news-item{cruise_cls}">')
            parts.append(f'<summary><span class="news-title">{title_text}</span></summary>')
            parts.append('<div class="news-body">')
            in_details = True
            continue

        # SOURCE: → source badge (inside summary via JS is complex; render inside body)
        m_source = re.match(r"^SOURCE:\s*(.+)$", s)
        if m_source and in_details:
            src = m_source.group(1)
            parts.append(f'<p class="news-source-line">{src}</p>')
            continue

        # IMAGE: → photo
        m_image = re.match(r"^IMAGE:\s*(https?://\S+)$", s)
        if m_image and in_details:
            img_url = m_image.group(1)
            parts.append(f'<img class="news-img" src="{img_url}" alt="" loading="lazy" onerror="this.style.display=\'none\'">')
            continue

        # ANALYSIS: → main paragraph
        m_analysis = re.match(r"^ANALYSIS:\s*(.+)$", s)
        if m_analysis and in_details:
            body_text = _md_bold(m_analysis.group(1))
            parts.append(f'<p>{body_text}</p>')
            continue

        # URL: → link (closes details if inside one)
        m_url = re.match(r"^URL:\s*(https?://\S+)$", s)
        if m_url:
            close_list()
            url = m_url.group(1)
            parts.append(f'<p class="article-url"><a href="{url}" target="_blank">{url}</a></p>')
            if in_details:
                close_details()
            continue

        # Bullet
        m3 = re.match(r"^[•\-\*·]\s+(.+)$", s)
        if m3:
            close_details()
            if not in_list:
                parts.append('<ul class="bullets">')
                in_list = True
            parts.append(f"<li>{_md_bold(m3.group(1))}</li>")
            continue

        # Empty line
        if not s:
            close_list()
            continue

        # Regular paragraph
        close_list()
        safe = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append(f"<p>{_md_bold(safe)}</p>")

    close_list()
    close_table()
    close_details()
    close_section()

    body = "\n  ".join(parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>High-End Tourism Newsletter — {today}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: Georgia, serif; background: #f0ede8; color: #1a1a1a; line-height: 1.75; }}
    .container {{ max-width: 820px; margin: 0 auto; padding: 24px 16px; }}

    .header {{ background: #1c3829; color: white; padding: 48px 40px; text-align: center; border-radius: 8px 8px 0 0; }}
    .header h1 {{ font-size: 22px; letter-spacing: 2px; text-transform: uppercase; font-weight: normal; margin-bottom: 10px; }}
    .header .week {{ font-size: 13px; color: #a8c5b0; letter-spacing: 1px; }}

    .section {{ background: white; margin-top: 14px; padding: 32px 36px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.07); }}
    .cruise-section {{ border-left: 5px solid #c9a84c; }}
    .expert-section {{ border-left: 5px solid #1c3829; background: #f7f9f7; }}

    .section-title {{ font-size: 12px; font-weight: bold; letter-spacing: 1.8px; text-transform: uppercase;
                      color: #1c3829; border-bottom: 2px solid #1c3829; padding-bottom: 10px; margin-bottom: 22px; }}
    .cruise-section .section-title {{ color: #7a5c10; border-color: #c9a84c; }}
    .expert-section .section-title {{ color: #1c3829; border-color: #1c3829; }}

    .sub-title {{ font-size: 12px; font-weight: bold; color: #3a6648; margin: 26px 0 10px;
                  letter-spacing: 0.5px; text-transform: uppercase; }}
    .cruise-section .sub-title {{ color: #9a7420; }}

    p {{ margin: 10px 0; font-size: 14.5px; }}
    .article-url {{ font-size: 12px; margin: 4px 0 8px; }}
    .article-url a {{ color: #3a6648; word-break: break-all; }}

    /* Collapsible news items */
    details.news-item {{
      border: 1px solid #e8e4df;
      border-radius: 6px;
      margin: 10px 0;
      overflow: hidden;
    }}
    details.news-item summary {{
      padding: 14px 18px;
      cursor: pointer;
      list-style: none;
      display: flex;
      align-items: center;
      gap: 12px;
      background: #faf9f7;
      user-select: none;
    }}
    details.news-item summary::-webkit-details-marker {{ display: none; }}
    details.news-item summary::before {{
      content: "▶";
      font-size: 9px;
      color: #3a6648;
      flex-shrink: 0;
      transition: transform 0.2s;
    }}
    details.news-item[open] summary::before {{ transform: rotate(90deg); }}
    details.news-item[open] summary {{ background: #f0ede8; }}
    .news-title {{ font-size: 15px; font-weight: bold; color: #1a1a1a; line-height: 1.4; }}
    details.cruise-item summary::before {{ color: #c9a84c; }}
    details.cruise-item .news-title {{ color: #7a5c10; }}

    .news-body {{ padding: 16px 20px; background: white; border-top: 1px solid #e8e4df; }}
    .news-source-line {{ font-size: 12px; color: #888; margin: 0 0 10px; font-style: italic; }}
    .news-img {{
      width: 100%;
      max-height: 220px;
      object-fit: cover;
      border-radius: 4px;
      margin-bottom: 14px;
      display: block;
    }}

    ul.bullets {{ list-style: none; padding: 0; margin: 12px 0; }}
    ul.bullets li {{ padding: 10px 0 10px 18px; border-bottom: 1px solid #f0ede8;
                     font-size: 14.5px; position: relative; }}
    ul.bullets li::before {{ content: "›"; position: absolute; left: 0; color: #3a6648;
                              font-weight: bold; font-size: 16px; line-height: 1.5; }}
    ul.bullets li:last-child {{ border-bottom: none; }}

    table.event-table {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13.5px; }}
    table.event-table th {{ background: #1c3829; color: white; padding: 10px 12px;
                            text-align: left; font-weight: normal; letter-spacing: 0.5px; }}
    table.event-table td {{ padding: 9px 12px; border-bottom: 1px solid #f0ede8; vertical-align: top; }}
    table.event-table tr:last-child td {{ border-bottom: none; }}
    table.event-table tr:nth-child(even) td {{ background: #faf9f7; }}

    .footer {{ text-align: center; padding: 28px 16px; font-size: 12px; color: #999; line-height: 1.8; }}
  </style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>High-End Tourism Newsletter</h1>
    <div class="week">Week of {today}</div>
  </div>

  {body}

  <div class="footer">
    Auto-generated · {today}<br>
    Claude Sonnet · Skift · ATTA · Condé Nast Traveler · Seatrade Cruise News · and other sources
  </div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
def send_email(pages_url: str, today: str) -> None:
    sender     = os.environ["GMAIL_USER"]
    recipients = [r.strip() for r in os.environ["RECIPIENT_EMAIL"].split(",")]
    password   = os.environ["GMAIL_APP_PASSWORD"]
    subject    = f"High-End Tourism Newsletter — week of {today}"

    body_text = (
        f"Hi,\n\n"
        f"The tourism newsletter for the week of {today} is now available:\n"
        f"{pages_url}\n\n"
        f"Agente Turismo · Fray León"
    )
    body_html = f"""<html><body style="font-family:sans-serif;font-size:14px;color:#111;">
<p>Hi,</p>
<p>The tourism newsletter for the week of {today} is now available:</p>
<p>
  <a href="{pages_url}"
     style="background:#1c3829;color:white;padding:12px 24px;border-radius:6px;
            text-decoration:none;font-weight:bold;display:inline-block;">
    Read Newsletter &rarr;
  </a>
</p>
<p style="color:#888;font-size:12px;">Agente Turismo · Fray León</p>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Agente Turismo <{sender}>"
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html",  "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(sender, password)
        srv.sendmail(sender, recipients, msg.as_string())

    print(f"  Mail enviado a: {', '.join(recipients)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("HIGH-END TOURISM NEWSLETTER")
    print("=" * 60)

    today = datetime.now().strftime("%d de %B de %Y")

    print("\n[1/4] Buscando noticias de los últimos 7 días...")
    articles   = fetch_news(days_back=7)
    small_ship = [a for a in articles if a["small_ship"]]
    print(f"  Total: {len(articles)} artículos ({len(small_ship)} cruceros ≤100 pax).")

    print("\n[2/4] Generando análisis con IA (Claude Sonnet)...")
    text = generate_newsletter(articles)

    print("\n[3/4] Generando HTML...")
    html = build_html(text, today)
    docs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    html_path = os.path.join(docs_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Guardado en {html_path}")

    pages_url  = os.environ.get("PAGES_URL", "")
    gmail_user = os.environ.get("GMAIL_USER", "")

    if pages_url and gmail_user:
        print("\n[4/4] Enviando mail...")
        send_email(pages_url, today)
    else:
        print("\n[4/4] Mail omitido (PAGES_URL o GMAIL_USER no configurados).")

    print("\nListo.")


if __name__ == "__main__":
    main()
