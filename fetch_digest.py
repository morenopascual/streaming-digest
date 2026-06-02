"""
fetch_digest.py
Agrega feeds RSS de medios de streaming/VOD, filtra por keywords
y guarda el resultado en digest.json.
Ejecutar manualmente:  python fetch_digest.py
Ejecutar en CI:        lo hace GitHub Actions automáticamente cada mañana.
"""
import json
import sys
from datetime import datetime, timezone, timedelta
import feedparser  # pip install feedparser

# ─────────────────────────────────────────────
# 1. FUENTES RSS
# ─────────────────────────────────────────────
FEEDS = [
    # ── Medios anglosajones premium ───────────────────────────────────────────
    ("Variety",                              "https://feeds.feedburner.com/variety/headlines"),
    ("Variety – TV (section)",               "https://variety.com/v/tv/feed/"),
    ("The Hollywood Reporter",               "https://www.hollywoodreporter.com/feed/"),
    ("Hollywood Reporter – TV (section)",    "https://www.hollywoodreporter.com/t/tv/feed/"),
    ("Deadline Hollywood",                   "https://deadline.com/feed/"),
    ("Deadline – TV (section)",              "https://deadline.com/v/tv/feed/"),
    ("The Verge",                            "https://www.theverge.com/rss/index.xml"),
    ("TechCrunch",                           "https://techcrunch.com/feed/"),
    ("Adweek",                               "https://www.adweek.com/feed/"),
    ("Ad Age",                               "https://adage.com/feeds/feed.rss"),
    ("Campaign",                             "https://www.campaignlive.com/feeds/rss"),
    ("Digiday",                              "https://digiday.com/feed/"),
    ("Press Gazette (UK)",                   "https://pressgazette.co.uk/feed/"),

    # ── Medios especializados streaming / broadcast ───────────────────────────
    ("Broadband TV News",                    "https://www.broadbandtvnews.com/feed/"),
    ("Advanced Television",                  "https://advanced-television.com/feed/"),
    ("Broadcasting & Cable / Next TV",       "https://www.nexttv.com/.rss/full/"),
    ("TVNewsCheck",                          "https://tvnewscheck.com/feed/"),
    ("Fierce Video",                         "https://www.fiercevideo.com/rss.xml"),
    ("TV Technology",                        "https://www.tvtechnology.com/rss"),
    ("TVB Europe",                           "https://www.tvbeurope.com/feed/"),
    ("VideoWeek",                            "https://videoweek.com/feed/"),
    ("Streaming Media",                      "https://www.streamingmedia.com/RSS/"),
    ("StreamTV Insider",                     "https://www.streamtvinsider.com/rss.xml"),
    ("The Media Leader (UK)",                "https://uk.themedialeader.com/feed/"),
    ("nScreenMedia",                         "https://nscreenmedia.com/feed/"),
    ("Screen Daily",                         "https://www.screendaily.com/rss"),
    ("C21 Media",                            "https://www.c21media.net/feed/"),
    ("MIDiA Research",                       "https://www.midiaresearch.com/blog/feed/"),
    ("The Audiencers",                       "https://theaudiencers.com/feed/"),

    # ── Medios españoles – audiovisual y streaming ────────────────────────────
    ("CVeintiuno (ES)",                      "https://cveintiuno.com/feed/"),
    ("TodoTVNews (ES)",                      "https://todotvnews.com/feed/"),
    ("Audiovisual451 (ES)",                  "https://www.audiovisual451.com/feed/"),
    ("Panorama Audiovisual (ES)",            "https://www.panoramaaudiovisual.com/feed/"),
    ("The Daily Television (ES)",            "https://www.thedailytelevision.com/feed/"),
    ("SatCesc (ES)",                         "https://satcesc.com/feed/"),

    # ── Medios españoles – marketing y publicidad ─────────────────────────────
    ("Marketing Directo (ES)",               "https://www.marketingdirecto.com/feed"),
    ("IPMARK (ES)",                          "https://ipmark.com/feed/"),
    ("ReasonWhy (ES)",                       "https://www.reasonwhy.es/rss.xml"),
    ("Dircomfidencial (ES)",                 "https://dircomfidencial.com/feed/"),
    ("Control Publicidad (ES)",              "https://www.ctrl.es/feed/"),
    ("Anuncios (ES)",                        "https://www.anuncios.com/rss/"),
    ("PuroMarketing (ES)",                   "https://www.puromarketing.com/feed/"),
    ("La Publicidad (ES)",                   "https://lapublicidad.net/feed/"),
    ("Programaticaly (ES)",                  "https://www.programaticaly.com/feed/"),
    ("AMI Info (ES/FR)",                     "https://www.ami.info/feed/"),

    # ── Medios españoles – tecnología y economía ──────────────────────────────
    ("Xataka (ES)",                          "https://www.xataka.com/feedburner.xml"),
    ("Xataka Smart TV (ES)",                 "https://www.xatakahome.com/tag/smart-tv/rss"),
    ("Hipertextual (ES)",                    "https://hipertextual.com/feed"),
    ("El Output (ES)",                       "https://eloutput.com/feed/"),
    ("MuyComputer (ES)",                     "https://www.muycomputer.com/feed/"),
    ("El País – Tecnología/Medios (ES)",     "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia"),
    ("Cinco Días – Empresas/Telecos (ES)",   "https://cincodias.elpais.com/rss/empresas.xml"),
    ("Expansión – Medios/Telecom (ES)",      "https://e00-expansion.uecdn.es/rss/tecnologia.xml"),
    ("El Economista – Telecom/Medios (ES)",  "https://www.eleconomista.es/rss/rss-economia-tecnologia.php"),
    ("Business Insider ES",                  "https://www.businessinsider.es/feed/"),
    ("Laboratorio de Periodismo (ES)",       "https://laboratoriodeperiodismo.org/feed/"),

    # ── CTV/Paid Media agencias España ────────────────────────────────────────
    ("Adsmurai – CTV/Paid Media (ES)",       "https://www.adsmurai.com/es/blog/rss.xml"),
    ("Making Science – Marketing/CTV (ES)",  "https://www.makingscience.es/feed/"),
    ("VivaConversion – CTV/Digital (ES)",    "https://vivaconversion.com/feed/"),

    # ── Medios alemanes ───────────────────────────────────────────────────────
    ("DWDL.de (DE)",                         "https://www.dwdl.de/rss/allethemen.xml"),
    ("Horizont Medien (DE)",                 "https://www.horizont.net/news/feed/medien/"),

    # ── Medios franceses e italianos ──────────────────────────────────────────
    ("Siècle Digital (FR)",                  "https://siecledigital.fr/feed/"),
    ("Prima Online (IT)",                    "https://www.primaonline.it/feed/"),
]

# ─────────────────────────────────────────────
# 2. PALABRAS CLAVE (insensible a mayúsculas)
# ─────────────────────────────────────────────
KEYWORDS = [
    # ── Plataformas de streaming ──────────────────────────────────────────────
    "netflix", "disney+", "disney plus", "max", "hbo", "hulu",
    "prime video", "apple tv", "peacock", "paramount+",
    "sky showtime", "fubotv", "youtube", "movistar+",
    "mitele", "rtl+", "joyn", "joyn+", "itvx", "sky",
    "claro video", "pluto tv", "tubi", "rakuten tv", "filmin",
    "atresplayer", "rtve play", "starzplay", "now tv", "crunchyroll",
    "sling tv", "samsung tv plus", "roku channel", "freevee",
    "viaplay", "canal+", "hbo max", "hotstar", "dstv", "viu", "dazn",
    "showdowntv", "howdy", "bet+", "zully", "tlmad",
    "globopop", "canela media", "vix", "espn",
    "channel 4", "m6+", "rtl group", "rtl deutschland",
    "prosiebensat", "prosieben", "joyn", "bedrock",
    "banijay", "secuoya", "mediahuis",

    # ── Formatos de contenido ─────────────────────────────────────────────────
    "microdrama", "microdramas", "vertical video", "vídeo vertical",
    "video vertical", "duanju", "short-form content", "short-form video",
    "clips feed", "vertical feed", "reelshort",
    "video podcast", "video podcasts", "podcast",
    "live streaming", "live show", "daily show",

    # ── Modelos de negocio ────────────────────────────────────────────────────
    "avod", "svod", "tvod", "fast", "ctv", "connected tv", "ott", "vod",
    "streaming", "digital advertising", "publicidad digital", "publicidad online",
    "programmatic", "ad-supported", "subscription", "suscripción",
    "freemium", "pay tv", "televisión de pago", "televisión en abierto",
    "pay per view", "ppv", "transactional vod", "hybrid model",
    "ad-funded", "ad-supported streaming", "branded content",
    "sponsorship", "patrocinio", "product placement",
    "addressable tv", "televisión direccionable",
    "bundling", "bundle", "super app", "superapp",
    "acquisition-first", "peak tv", "long tail",
    "content discovery", "subscriber retention", "retention funnel",
    "fandom", "superfan", "direct-to-consumer", "d2c",
    "ad-free", "price hike", "churn", "arpu",

    # ── Empresas ──────────────────────────────────────────────────────────────
    "warner bros", "warner bros discovery", "wbd",
    "nbcuniversal", "comcast", "rtl group",
    "televisaunivision", "paramount global", "paramount skydance",
    "mfe", "mediaset", "amazon", "disney", "apple",
    "google tv", "samsung tv", "sony pictures",
    "universal pictures", "lionsgate", "fox", "amc networks",
    "sky group", "vodafone tv", "orange tv", "altice", "telefónica",
    "at&t", "discovery", "fremantle", "itv studios", "bbc studios",
    "itv", "channel 4", "bbc", "tf1", "m6", "rtve", "atresmedia",
    "movistar plus", "mediaset españa", "netflix", "spotify",
    "roku", "tiktok", "meta", "snap", "snapchat",

    # ── Tecnología / dispositivos ─────────────────────────────────────────────
    "smart tv", "tizen", "fire tv", "chromecast",
    "set-top box", "streaming device",
    "android tv", "webos", "tvos", "vidaa", "titan os",
    "hisense", "lg tv", "samsung smart tv", "apple tv 4k",
    "playstation", "xbox", "hbbtv", "iptv", "ott box",
    "google tv os", "tv os", "tivo",

    # ── Publicidad, medición y datos ──────────────────────────────────────────
    "programmatic advertising", "publicidad programática", "adtech", "martech",
    "ssp", "dsp", "data management platform", "dmp",
    "customer data platform", "cdp",
    "audience measurement", "medición de audiencias",
    "cross-media measurement", "cross-platform measurement",
    "viewability", "brand safety",
    "cpv", "cpc", "cpm", "ctr", "grps", "trps",
    "first-party data", "third-party cookies", "cookieless",
    "privacy sandbox", "brand lift", "incremental reach",
    "incrementalidad", "multitouch attribution",
    "marketing mix modeling", "mmx", "attribution modeling",
    "home screen ads", "shoppable ads", "shoppable video",
    "interactive ads", "pre-roll", "full-funnel",
    "attention measurement", "acr data",
    "ctv measurement", "unified measurement",
    "addressable advertising", "programmatic tv",
    "upfronts", "brandcast", "newfronts", "upfront 2026",

    # ── Inteligencia artificial ───────────────────────────────────────────────
    "artificial intelligence", "inteligencia artificial",
    "machine learning", "deep learning",
    "ai-generated content", "generative ai", "ia generativa",
    "chatbot", "llm", "recommendation engine",
    "algoritmo de recomendación", "personalized recommendations",
    "content personalization", "automated ad buying",
    "campaign optimization", "predictive analytics",
    "computer vision", "natural language processing", "nlp",
    "speech to text",
    "ai video", "deepfake detection", "ai covers", "ai labeling",
    "ai voice search", "ai overviews", "gemini",
    "agentic ai", "agentic ads", "void ai", "seedance",
    "ai-generated show", "ai content", "ai tool", "ai search",
    "chatgpt", "perplexity", "openai", "sora",

    # ── Redes sociales / creadores ────────────────────────────────────────────
    "social media", "redes sociales", "facebook", "instagram", "tiktok",
    "twitter", "snapchat", "pinterest", "linkedin", "twitch",
    "youtube shorts", "instagram reels",
    "influencers", "creadores de contenido", "creator economy",
    "ugc", "user generated content", "fan communities",
    "social commerce", "brand collaborations",

    # ── Industria de medios y televisión ─────────────────────────────────────
    "broadcast tv", "televisión lineal", "free-to-air", "fta",
    "cable tv", "satellite tv", "pay tv operators",
    "public service broadcasting", "psb",
    "news channels", "sports channels", "movie channels",
    "media and entertainment", "medios de comunicación",
    "industria audiovisual", "formatos de entretenimiento",
    "unscripted", "scripted series", "miniseries",
    "showrunner", "writers room", "pilot season",
    "content licensing", "licencias de contenido",
    "windowing", "ventanas de explotación",
    "international distribution", "distribución internacional",
    "la screenings", "seriesmania",

    # ── Deportes y derechos ───────────────────────────────────────────────────
    "fifa world cup", "copa mundial", "world cup 2026",
    "mls", "nfl", "serie a", "laliga", "sports rights",
    "live sports", "sports streaming", "sports ad spend",
    "sports content", "derechos deportivos",

    # ── Regulación y políticas ────────────────────────────────────────────────
    "media regulation", "regulación de medios", "audiovisual regulation",
    "eu audiovisual", "quotas", "cuotas de pantalla",
    "csr", "brand purpose", "advertising standards",
    "data protection", "gdpr", "privacy regulation",
    "children advertising", "age-gating", "content rating",
    "ofcom", "investment quota", "cuota inversión",
    "licence fee", "luxembourg declaration",
    "copyright infringement", "ai regulation",
    "media regulation eu", "streaming rules",

    # ── Medios y publishers (impacto de IA / tráfico) ─────────────────────────
    "google discover", "dark social", "zero-click",
    "publisher", "paywall", "news aggregator",
    "propensity", "reader revenue", "subscription growth",
    "search traffic", "organic traffic", "ai overviews",
]

# ─────────────────────────────────────────────
# 3. EXCLUSIONES
# ─────────────────────────────────────────────

# Términos que excluyen el artículo de forma absoluta (cadena exacta en minúsculas)
EXCLUDE_TERMS = [
    "max verstappen",
    "max holloway",       # UFC — colisión con token "max" (HBO Max)
    "formula 1",          # motorsport, bajo interés para el sector
    "f1 grand prix",
    "hair oiling",        # Xataka lifestyle off-topic
    "frutos secos",       # Xataka lifestyle off-topic
    "ciguena",            # Xataka off-topic
    "yates más caros",    # Xataka off-topic
    "ferrari luce",       # Xataka automóvil
    "hidrogeno",          # Xataka energía
    "smartwatch",         # Xataka gadgets sin relación
    "portátil windows",   # Xataka hardware off-topic
    "pila de hidrógeno",  # Xataka energía
]

# Cuando "disney" aparece pero en contexto de parques o cine físico, excluir
DISNEY_EXCLUDE_TOPICS = [
    "theme park", "disneyland", "disney world",
    "pixar", "marvel", "star wars",
    "box office",   # añadido: evita artículos de taquilla sin relación con streaming
]

# ─────────────────────────────────────────────
# 4. FUNCIONES DE FILTRADO
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
    # Sin fecha: incluir por defecto (mejor falso positivo que perder noticias)
    return True


def is_relevant(entry):
    """Devuelve True si el artículo contiene al menos una keyword y no está excluido."""
    text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()

    # Exclusiones absolutas
    for term in EXCLUDE_TERMS:
        if term in text:
            return False

    # Caso especial Disney: excluir si aparece solo en contexto parques/cine
    if "disney" in text and "disney+" not in text and "disney plus" not in text:
        if any(topic in text for topic in DISNEY_EXCLUDE_TOPICS):
            return False

    # Al menos una keyword debe aparecer
    return any(kw in text for kw in KEYWORDS)


# ─────────────────────────────────────────────
# 5. LÓGICA PRINCIPAL
# ─────────────────────────────────────────────

def fetch_feed(name, url):
    """Descarga y parsea un feed RSS. Devuelve (lista_artículos, error_o_None)."""
    try:
        feed = feedparser.parse(url, request_headers={
            "User-Agent": "Mozilla/5.0 (compatible; StreamingDigestBot/1.0)"
        })
        if feed.bozo and not feed.entries:
            return [], f"Error al parsear el feed: {feed.bozo_exception}"

        articles = []
        for entry in feed.entries:
            if is_recent(entry) and is_relevant(entry):
                pub = ""
                t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
                if t:
                    pub = datetime(*t[:6], tzinfo=timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
                articles.append({
                    "title":     entry.get("title", "(sin título)"),
                    "url":       entry.get("link", ""),
                    "published": pub,
                    "source":    name,
                })
        return articles, None

    except Exception as e:
        return [], str(e)


def main():
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}] "
          f"Iniciando fetch de {len(FEEDS)} feeds...")

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
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "date":           datetime.now(timezone.utc).strftime("%d/%m/%Y"),
        "window_hours":   WINDOW_HOURS,
        "total_articles": total_articles,
        "sources":        sources,
    }

    with open("digest.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nTotal artículos relevantes: {total_articles}")
    print("Fichero guardado: digest.json")


if __name__ == "__main__":
    main()
