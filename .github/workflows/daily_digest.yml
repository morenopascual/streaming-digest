"""
fetch_digest.py
Agrega feeds RSS de medios de streaming/VOD, filtra por keywords
y guarda el resultado en digest.json.

Ejecutar manualmente:  python fetch_digest.py
Ejecutar en CI:        lo hace GitHub Actions automáticamente cada mañana.
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import feedparser  # pip install feedparser
import requests    # pip install requests

# ─────────────────────────────────────────────
# 1. FUENTES RSS
# ─────────────────────────────────────────────
FEEDS = [
    ("Variety",                  "https://feeds.feedburner.com/variety/headlines"),
    ("The Hollywood Reporter",   "https://www.hollywoodreporter.com/feed/"),
    ("Deadline Hollywood",       "https://deadline.com/feed/"),
    ("TechCrunch",               "https://techcrunch.com/feed/"),
    ("Digiday",                  "https://digiday.com/feed/"),
    ("Broadband TV News",        "https://www.broadbandtvnews.com/feed/"),
    ("Marketing Directo (ES)",   "https://www.marketingdirecto.com/feed"),
    ("Xataka (ES)",              "https://www.xataka.com/feedburner.xml"),
    ("IPMARK (ES)",              "https://ipmark.com/feed/"),
    ("DWDL.de (DE)",             "https://www.dwdl.de/rss/allethemen.xml"),
    ("Horizont Medien (DE)",     "https://www.horizont.net/news/feed/medien/"),
]

# ─────────────────────────────────────────────
# 2. PALABRAS CLAVE (insensible a mayúsculas)
# ─────────────────────────────────────────────
KEYWORDS = [
    # Plataformas
    "netflix", "disney+", "max", "hbo", "hulu", "prime video", "apple tv",
    "peacock", "paramount+", "sky showtime", "fubotv", "youtube", "movistar+",
    "mitele", "rtl+", "joyn", "itvx", "sky", "claro video",
    # Modelos de negocio
    "avod", "svod", "tvod", "fast", "ctv", "connected tv", "ott", "vod",
    "streaming", "digital advertising", "publicidad digital", "publicidad online",
    "programmatic", "ad-supported", "subscription", "suscripción",
    # Empresas
    "warner bros", "nbcuniversal", "comcast", "rtl group", "prosieben",
    "televisaunivision", "paramount global", "mfe", "mediaset", "amazon",
    "disney", "apple", "google tv", "samsung tv",
    # Tecnología
    "smart tv", "tizen", "google tv", "fire tv", "chromecast", "roku",
    "set-top box", "streaming device",
]

# Términos que EXCLUYEN el artículo
EXCLUDE_TERMS = [
    "max verstappen",
]

# Categorías Disney que se excluyen (cuando Disney aparece solo en contexto cine/parques)
DISNEY_EXCLUDE_TOPICS = [
    "box office", "theme park", "disneyland", "disney world",
    "pixar", "marvel", "star wars",
]

# ─────────────────────────────────────────────
# 3. FUNCIONES DE FILTRADO
# ─────────────────────────────────────────────
WINDOW_HOURS = 48

def is_recent(entry):
    """Devuelve True si el artículo tiene menos de WINDOW_HOURS horas."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                dt = datetime(*t[:6], tzinfo=timezone.utc)
                return datetime.now(timezone.utc) - dt < timedelta(hours=WINDOW_HOURS)
            except Exception:
                pass
    # Si no hay fecha, incluir por defecto (mejor un falso positivo que perder noticias)
    return True

def is_relevant(entry):
    """Devuelve True si el artículo contiene al menos una keyword y no está excluido."""
    text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()

    # Exclusiones absolutas
    for term in EXCLUDE_TERMS:
        if term in text:
            return False

    # Caso especial Disney: excluir si Disney aparece pero el tema es parques/cine
    if "disney" in text and "disney+" not in text and "disney plus" not in text:
        if any(topic in text for topic in DISNEY_EXCLUDE_TOPICS):
            return False

    # Al menos una keyword debe aparecer
    return any(kw in text for kw in KEYWORDS)

# ─────────────────────────────────────────────
# 4. LÓGICA PRINCIPAL
# ─────────────────────────────────────────────
def fetch_feed(name, url):
    """Descarga y parsea un feed RSS. Devuelve (lista_artículos, error_o_None)."""
    try:
        # feedparser maneja gzip, encodings raros y feeds rotos
        feed = feedparser.parse(url, request_headers={
            "User-Agent": "Mozilla/5.0 (compatible; StreamingDigestBot/1.0)"
        })

        if feed.bozo and not feed.entries:
            return [], f"Error al parsear el feed: {feed.bozo_exception}"

        articles = []
        for entry in feed.entries:
            if is_recent(entry) and is_relevant(entry):
                # Fecha legible
                pub = ""
                t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
                if t:
                    pub = datetime(*t[:6], tzinfo=timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

                articles.append({
                    "title": entry.get("title", "(sin título)"),
                    "url":   entry.get("link", ""),
                    "published": pub,
                    "source": name,
                })

        return articles, None

    except Exception as e:
        return [], str(e)


def main():
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}] Iniciando fetch de {len(FEEDS)} feeds...")

    sources = []
    total_articles = 0

    for name, url in FEEDS:
        print(f"  → {name}... ", end="", flush=True)
        articles, error = fetch_feed(name, url)
        total_articles += len(articles)
        print(f"{len(articles)} artículos" + (f" (ERROR: {error})" if error else ""))

        sources.append({
            "name":     name,
            "url":      url,
            "articles": articles,
            "error":    error,
        })

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date":         datetime.now(timezone.utc).strftime("%d/%m/%Y"),
        "window_hours": WINDOW_HOURS,
        "total_articles": total_articles,
        "sources":      sources,
    }

    with open("digest.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nTotal artículos relevantes: {total_articles}")
    print("Fichero guardado: digest.json")


if __name__ == "__main__":
    main()
