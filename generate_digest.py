"""
Digest Streaming & VOD — Atresmedia
Genera el index.html con los artículos más relevantes de las últimas 48h.
"""

import os
import json
import feedparser
import anthropic
from datetime import datetime, timezone, timedelta

# ─── FUENTES RSS ──────────────────────────────────────────────────────────────

FEEDS = [
    ("Variety",               "https://feeds.feedburner.com/variety/headlines"),
    ("The Hollywood Reporter","https://www.hollywoodreporter.com/feed/"),
    ("Deadline Hollywood",    "https://deadline.com/feed/"),
    ("TechCrunch",            "https://techcrunch.com/feed/"),
    ("Digiday",               "https://digiday.com/feed/"),
    ("Broadband TV News",     "https://www.broadbandtvnews.com/feed/"),
    ("Marketing Directo",     "https://www.marketingdirecto.com/feed"),
    ("Xataka",                "https://www.xataka.com/feedburner.xml"),
    ("IPMARK",                "https://ipmark.com/feed/"),
    ("DWDL.de",               "http://www.dwdl.de/rss/allethemen.xml"),
    ("Horizont Medien",       "https://www.horizont.net/news/feed/medien/"),
]

# ─── FILTROS ──────────────────────────────────────────────────────────────────

KEYWORDS = [
    "netflix","disney+","max","hbo","hulu","prime video","apple tv","peacock",
    "paramount+","sky showtime","fubotv","youtube","movistar+","mitele","rtl+",
    "joyn","itvx","sky","claro video","avod","svod","tvod","fast","ctv",
    "connected tv","ott","vod","streaming","digital advertising",
    "publicidad digital","publicidad online","programmatic","ad-supported",
    "subscription","suscripción","warner bros discovery","nbcuniversal",
    "comcast","rtl group","prosieben","televisaunivision","paramount global",
    "mfe","mediaset","amazon","disney","google tv","samsung tv","smart tv",
    "tizen","fire tv","chromecast","roku",
]

EXCLUDE = ["max verstappen","verstappen"]

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def is_recent(entry, hours=48):
    pub = entry.get("published_parsed") or entry.get("updated_parsed")
    if not pub:
        return True
    try:
        dt = datetime(*pub[:6], tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc) - timedelta(hours=hours)
    except Exception:
        return True


def is_relevant(title, summary=""):
    text = (title + " " + summary).lower()
    if any(ex in text for ex in EXCLUDE):
        return False
    return any(kw in text for kw in KEYWORDS)


def short_url(url):
    url = url.replace("https://","").replace("http://","").replace("www.","")
    return url[:55] + "…" if len(url) > 55 else url


def format_date(entry):
    pub = entry.get("published_parsed") or entry.get("updated_parsed")
    if not pub:
        return "hoy"
    try:
        dt = datetime(*pub[:6], tzinfo=timezone.utc)
        months = ["ene","feb","mar","abr","may","jun",
                  "jul","ago","sep","oct","nov","dic"]
        return f"{dt.day} {months[dt.month-1]}"
    except Exception:
        return "hoy"

# ─── FETCH ────────────────────────────────────────────────────────────────────

def fetch_articles():
    articles = []
    for source, url in FEEDS:
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent":"Mozilla/5.0"})
            for entry in feed.entries:
                title   = entry.get("title","").strip()
                summary = entry.get("summary","")
                link    = entry.get("link","")
                if title and link and is_recent(entry) and is_relevant(title, summary):
                    articles.append({
                        "source":  source,
                        "title":   title,
                        "url":     link,
                        "url_short": short_url(link),
                        "date":    format_date(entry),
                        "summary": summary[:400],
                    })
        except Exception as e:
            print(f"  ✗ {source}: {e}")
    print(f"  → {len(articles)} artículos relevantes encontrados")
    return articles

# ─── GENERATE ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres un editor especializado en el sector del streaming, VOD y publicidad digital.
Tu tarea es generar el HTML completo del digest diario de Atresmedia a partir de artículos en JSON.
Devuelves ÚNICAMENTE el HTML completo, sin markdown, sin ``` ni explicaciones."""

def generate_html(articles, template_html):
    today = datetime.now().strftime("%d/%m/%Y")
    articles_json = json.dumps(articles, ensure_ascii=False, indent=2)

    user_prompt = f"""Fecha de hoy: {today}

Artículos disponibles (JSON):
{articles_json}

CATEGORÍAS a usar (solo las que tengan contenido):
• PLATAFORMAS Y SECTOR  → plataformas streaming, OTT, modelos SVOD/AVOD/FAST
• PUBLICIDAD            → inversión publicitaria, ad-tech, CTV advertising
• IA                    → inteligencia artificial aplicada al audiovisual/media
• RESULTADOS FINANCIEROS → earnings, resultados trimestrales/anuales
• MEDIOS Y TELEVISIÓN   → broadcasters, grupos de medios, TV lineal
• CTV                   → Connected TV, smart TVs, dispositivos, ecosistemas
• REDES SOCIALES        → TikTok, Instagram, YouTube como plataformas sociales
• REGULACIÓN            → legislación, reguladores, política audiovisual
• ESTUDIOS E INFORMES   → research, datos de mercado, audiencias

REGLAS:
- Excluye titulares sobre Disney NO relacionados con Disney+ (cine, parques, Marvel, Star Wars)
- Excluye cualquier mención a Max Verstappen
- Si no hay artículos para una categoría, omítela
- El análisis final debe incluir "Temas del día" (4-5 puntos) y "Para seguir" (2-3 tendencias relevantes para Atresmedia/atresplayer)
- Mantén el botón "↻ Actualizar" en el header

Genera el HTML completo con los nuevos artículos. Usa EXACTAMENTE el mismo CSS del template.
Template actual:
{template_html}"""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    html = msg.content[0].text.strip()
    # Strip markdown fences if present
    for fence in ("```html", "```"):
        if html.startswith(fence):
            html = html[len(fence):]
    if html.endswith("```"):
        html = html[:-3]
    return html.strip()

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("1/3  Leyendo feeds RSS…")
    articles = fetch_articles()
    if not articles:
        print("Sin artículos relevantes. No se actualiza index.html.")
        return

    print("2/3  Cargando template…")
    with open("index.html", "r", encoding="utf-8") as f:
        template = f.read()

    print("3/3  Generando HTML con Claude…")
    html = generate_html(articles, template)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✓  index.html actualizado")


if __name__ == "__main__":
    main()
