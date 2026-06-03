"""
Digest Streaming & VOD — Atresmedia
Genera el index.html con los artículos más relevantes de las últimas 48h.
"""
import os
import re
import json
import feedparser
import anthropic
from datetime import datetime, timezone, timedelta

# ─── FUENTES RSS ──────────────────────────────────────────────────────────────
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

# ─── FILTROS ──────────────────────────────────────────────────────────────────
KEYWORDS = [
    # ── Plataformas ───────────────────────────────────────────────────────────
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
    "prosiebensat", "prosieben", "bedrock", "banijay", "secuoya",
    # ── Formatos de contenido ─────────────────────────────────────────────────
    "microdrama", "microdramas", "vertical video", "vídeo vertical",
    "video vertical", "duanju", "short-form content", "short-form video",
    "clips feed", "vertical feed", "reelshort",
    "video podcast", "video podcasts", "podcast", "live streaming", "live show",
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
    "nbcuniversal", "comcast", "televisaunivision", "paramount global",
    "paramount skydance", "mfe", "mediaset", "amazon", "disney", "apple",
    "google tv", "samsung tv", "sony pictures", "universal pictures",
    "lionsgate", "fox", "amc networks", "sky group", "vodafone tv",
    "orange tv", "altice", "telefónica", "at&t", "discovery",
    "fremantle", "itv studios", "bbc studios", "itv", "channel 4",
    "bbc", "tf1", "m6", "rtve", "atresmedia", "movistar plus",
    "mediaset españa", "spotify", "roku", "tiktok", "meta", "snap",
    # ── Tecnología / dispositivos ─────────────────────────────────────────────
    "smart tv", "tizen", "fire tv", "chromecast", "set-top box",
    "streaming device", "android tv", "webos", "tvos", "vidaa", "titan os",
    "hisense", "lg tv", "samsung smart tv", "apple tv 4k",
    "playstation", "xbox", "hbbtv", "iptv", "ott box", "tivo",
    # ── Publicidad, medición y datos ──────────────────────────────────────────
    "programmatic advertising", "publicidad programática", "adtech", "martech",
    "ssp", "dsp", "data management platform", "dmp",
    "customer data platform", "cdp",
    "audience measurement", "medición de audiencias",
    "cross-media measurement", "cross-platform measurement",
    "viewability", "brand safety", "cpv", "cpc", "cpm", "ctr", "grps", "trps",
    "first-party data", "third-party cookies", "cookieless",
    "privacy sandbox", "brand lift", "incremental reach",
    "incrementalidad", "multitouch attribution",
    "marketing mix modeling", "mmx", "attribution modeling",
    "home screen ads", "shoppable ads", "shoppable video",
    "interactive ads", "pre-roll", "full-funnel",
    "attention measurement", "acr data", "ctv measurement",
    "unified measurement", "addressable advertising", "programmatic tv",
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
    "speech to text", "ai video", "deepfake detection", "ai covers",
    "ai labeling", "ai voice search", "ai overviews", "gemini",
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
    "live sports", "sports streaming", "sports ad spend", "derechos deportivos",
    # ── Regulación y políticas ────────────────────────────────────────────────
    "media regulation", "regulación de medios", "audiovisual regulation",
    "eu audiovisual", "quotas", "cuotas de pantalla",
    "csr", "brand purpose", "advertising standards",
    "data protection", "gdpr", "privacy regulation",
    "children advertising", "age-gating", "content rating",
    "ofcom", "investment quota", "cuota inversión",
    "licence fee", "luxembourg declaration",
    "copyright infringement", "ai regulation", "streaming rules",
    # ── Medios y publishers ───────────────────────────────────────────────────
    "google discover", "dark social", "zero-click",
    "publisher", "paywall", "news aggregator",
    "propensity", "reader revenue", "subscription growth",
    "search traffic", "organic traffic",
]

EXCLUDE = [
    "max verstappen",
    "max holloway",
    "formula 1",
    "f1 grand prix",
    "hair oiling",
    "frutos secos",
    "ciguena",
    "yates más caros",
    "ferrari luce",
    "hidrogeno",
    "smartwatch",
    "portátil windows",
    "pila de hidrógeno",
]

DISNEY_EXCLUDE_TOPICS = [
    "theme park", "disneyland", "disney world",
    "pixar", "marvel", "star wars", "box office",
]

# Máximo de artículos enviados a Claude (evita timeouts y coste excesivo)
MAX_ARTICLES = 60

# ─── ELEMENTOS UI FIJOS ───────────────────────────────────────────────────────
HEADER_HTML = """\
<div class="site-header">
  <div>
    <h1>Digest Streaming &amp; VOD</h1>
    <p>{date} &nbsp;·&nbsp; Atresmedia</p>
  </div>
  <div style="display:flex;gap:8px;flex-shrink:0">
    <a href="board.html" class="btn-update" style="background:#f2f2f7;color:#1c1c1e">📋 Tablero</a>
    <button class="btn-update btn-select" id="btn-select" onclick="toggleSelect()">Seleccionar</button>
    <button class="btn-update" id="update-btn" onclick="triggerUpdate()">↻ Actualizar</button>
  </div>
</div>"""

SELECT_FIX_SCRIPT = """\
<script>
/* Fix selección de cards: las cards son <a href>, sin esto el navegador
   abre el enlace antes de que el JS pueda marcarla como seleccionada. */
document.addEventListener('click', function(e) {
  var card = e.target.closest('.card');
  if (!card || !document.body.classList.contains('select-mode')) return;
  e.preventDefault();
  card.classList.toggle('selected');
  var n   = document.querySelectorAll('.card.selected').length;
  var txt = document.getElementById('save-bar-text');
  var btn = document.getElementById('btn-save');
  var bar = document.getElementById('save-bar');
  if (txt) txt.textContent = n + (n === 1 ? ' noticia seleccionada' : ' noticias seleccionadas');
  if (btn) btn.disabled = n === 0;
  if (bar) bar.classList.toggle('visible', n > 0);
}, true);
</script>"""

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
    if "disney" in text and "disney+" not in text and "disney plus" not in text:
        if any(topic in text for topic in DISNEY_EXCLUDE_TOPICS):
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
                        "source":    source,
                        "title":     title,
                        "url":       link,
                        "url_short": short_url(link),
                        "date":      format_date(entry),
                        "summary":   summary[:400],
                    })
        except Exception as e:
            print(f"  ✗ {source}: {e}")

    # Limitar artículos para evitar timeouts y coste excesivo
    articles = articles[:MAX_ARTICLES]
    print(f"  → {len(articles)} artículos enviados a Claude (máx. {MAX_ARTICLES})")
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
- El análisis final debe incluir "Temas del día" (4-5 puntos) y "Para seguir" (2-3 tendencias para Atresmedia/atresplayer)
- NO incluyas el bloque <div class="site-header">...</div> ni ningún <script> al final — el script los gestiona automáticamente
Genera el HTML completo. Usa EXACTAMENTE el mismo CSS del template.
Template actual:
{template_html}"""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    html = msg.content[0].text.strip()
    for fence in ("```html", "```"):
        if html.startswith(fence):
            html = html[len(fence):]
    if html.endswith("```"):
        html = html[:-3]
    return html.strip()

# ─── POST-PROCESADO ───────────────────────────────────────────────────────────
def inject_header(html, date):
    """Inyecta el header canónico justo después de <body>.
    Primero elimina cualquier site-header que Claude haya generado,
    luego inserta el nuestro — así funciona tanto si Claude lo incluye
    como si no."""
    header = HEADER_HTML.format(date=date)
    # Eliminar cualquier site-header existente (por si Claude lo generó)
    html = re.sub(
        r'<div class=["\']site-header["\']>[\s\S]*?</div>\s*</div>',
        '',
        html, count=1
    )
    # Inyectar el nuestro justo después de <body>
    if '<body>' in html:
        return html.replace('<body>', '<body>\n' + header, 1)
    return html

def inject_select_fix(html):
    """Inyecta el fix de selección justo antes de </body>."""
    tag = "</body>"
    if tag in html:
        return html.replace(tag, SELECT_FIX_SCRIPT + "\n" + tag, 1)
    return html + "\n" + SELECT_FIX_SCRIPT

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

    today = datetime.now().strftime("%d/%m/%Y")

    print("3/3  Generando HTML con Claude Haiku…")
    html = generate_html(articles, template)

    # Post-procesado: blindar UI independientemente de lo que Claude produzca
    html = inject_header(html, today)
    html = inject_select_fix(html)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✓  index.html actualizado")

if __name__ == "__main__":
    main()
