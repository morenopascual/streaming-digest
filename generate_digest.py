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
    ("CVeintiuno (ES)",                      "https://cveintiuno.com/feed/"),
    ("TodoTVNews (ES)",                      "https://todotvnews.com/feed/"),
    ("Audiovisual451 (ES)",                  "https://www.audiovisual451.com/feed/"),
    ("Panorama Audiovisual (ES)",            "https://www.panoramaaudiovisual.com/feed/"),
    ("The Daily Television (ES)",            "https://www.thedailytelevision.com/feed/"),
    ("SatCesc (ES)",                         "https://satcesc.com/feed/"),
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
    ("Xataka (ES)",                          "https://www.xataka.com/feedburner.xml"),
    ("Xataka Smart TV (ES)",                 "https://www.xatakahome.com/tag/smart-tv/rss"),
    ("Hipertextual (ES)",                    "https://hipertextual.com/feed"),
    ("El País – Tecnología/Medios (ES)",     "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia"),
    ("Cinco Días – Empresas/Telecos (ES)",   "https://cincodias.elpais.com/rss/empresas.xml"),
    ("Business Insider ES",                  "https://www.businessinsider.es/feed/"),
    ("Laboratorio de Periodismo (ES)",       "https://laboratoriodeperiodismo.org/feed/"),
    ("DWDL.de (DE)",                         "https://www.dwdl.de/rss/allethemen.xml"),
    ("Horizont Medien (DE)",                 "https://www.horizont.net/news/feed/medien/"),
    ("Siècle Digital (FR)",                  "https://siecledigital.fr/feed/"),
    ("Prima Online (IT)",                    "https://www.primaonline.it/feed/"),
]

# ─── FILTROS ──────────────────────────────────────────────────────────────────
KEYWORDS = [
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
    "microdrama", "microdramas", "vertical video", "vídeo vertical",
    "video vertical", "duanju", "short-form content", "short-form video",
    "clips feed", "vertical feed", "reelshort",
    "video podcast", "video podcasts", "podcast", "live streaming", "live show",
    "avod", "svod", "tvod", "fast", "ctv", "connected tv", "ott", "vod",
    "streaming", "digital advertising", "publicidad digital", "publicidad online",
    "programmatic", "ad-supported", "subscription", "suscripción",
    "freemium", "pay tv", "televisión de pago", "televisión en abierto",
    "pay per view", "ppv", "transactional vod", "hybrid model",
    "ad-funded", "branded content", "sponsorship", "patrocinio",
    "addressable tv", "bundling", "bundle", "super app",
    "content discovery", "subscriber retention", "fandom", "superfan",
    "direct-to-consumer", "d2c", "ad-free", "price hike", "churn", "arpu",
    "warner bros", "warner bros discovery", "wbd",
    "nbcuniversal", "comcast", "televisaunivision", "paramount global",
    "paramount skydance", "mfe", "mediaset", "amazon", "disney", "apple",
    "google tv", "samsung tv", "sony pictures", "universal pictures",
    "lionsgate", "fox", "amc networks", "sky group", "vodafone tv",
    "orange tv", "altice", "telefónica", "at&t", "discovery",
    "fremantle", "itv studios", "bbc studios", "itv", "channel 4",
    "bbc", "tf1", "m6", "rtve", "atresmedia", "movistar plus",
    "mediaset españa", "spotify", "roku", "tiktok", "meta", "snap",
    "smart tv", "tizen", "fire tv", "chromecast", "set-top box",
    "android tv", "webos", "tvos", "vidaa", "titan os",
    "hisense", "lg tv", "playstation", "xbox", "hbbtv", "iptv", "tivo",
    "programmatic advertising", "publicidad programática", "adtech", "martech",
    "ssp", "dsp", "dmp", "cdp", "audience measurement", "medición de audiencias",
    "viewability", "brand safety", "cpm", "ctr",
    "first-party data", "cookieless", "brand lift",
    "home screen ads", "shoppable ads", "pre-roll", "full-funnel",
    "attention measurement", "acr data", "upfronts", "brandcast", "newfronts",
    "artificial intelligence", "inteligencia artificial",
    "machine learning", "ai-generated content", "generative ai", "ia generativa",
    "chatbot", "llm", "recommendation engine", "content personalization",
    "ai video", "deepfake detection", "ai overviews", "gemini",
    "agentic ai", "chatgpt", "perplexity", "openai", "sora",
    "social media", "redes sociales", "facebook", "instagram", "tiktok",
    "twitter", "snapchat", "twitch", "youtube shorts",
    "influencers", "creator economy", "ugc", "social commerce",
    "broadcast tv", "televisión lineal", "free-to-air", "fta",
    "cable tv", "satellite tv", "public service broadcasting",
    "media and entertainment", "medios de comunicación",
    "industria audiovisual", "unscripted", "scripted series",
    "content licensing", "windowing", "upfronts", "seriesmania",
    "fifa world cup", "copa mundial", "world cup 2026",
    "mls", "nfl", "laliga", "sports rights", "live sports", "derechos deportivos",
    "media regulation", "regulación de medios", "audiovisual regulation",
    "eu audiovisual", "quotas", "gdpr", "ofcom", "investment quota",
    "copyright infringement", "ai regulation", "streaming rules",
    "google discover", "publisher", "paywall", "reader revenue",
    "search traffic", "organic traffic",
]

EXCLUDE = [
    "max verstappen", "max holloway", "formula 1", "f1 grand prix",
    "hair oiling", "frutos secos", "ciguena", "ferrari luce",
    "smartwatch", "portátil windows", "pila de hidrógeno",
]

DISNEY_EXCLUDE_TOPICS = [
    "theme park", "disneyland", "disney world",
    "pixar", "marvel", "star wars", "box office",
]

MAX_ARTICLES = 60

# ─── UI: CSS INTERACTIVO ──────────────────────────────────────────────────────
# CSS que Claude no genera de forma fiable — se inyecta siempre en <head>
EXTRA_CSS = """<style>
/* ── Header layout ── */
.site-header{background:#fff;border-bottom:1px solid #e5e5ea;padding:16px 20px;position:sticky;top:0;z-index:10;display:flex !important;align-items:center !important;justify-content:space-between !important;gap:12px}
.site-header h1{font-size:19px;font-weight:700;letter-spacing:-.2px}
.site-header p{font-size:13px;color:#8e8e93;margin-top:3px}
/* ── Botones header ── */
.btn-update{display:inline-flex !important;align-items:center;gap:5px;padding:8px 14px;background:#007aff;color:#fff !important;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;flex-shrink:0;transition:opacity .15s;text-decoration:none}
.btn-update:hover{opacity:.85}
.btn-update:disabled{opacity:.5;cursor:default}
.btn-select{background:#f2f2f7 !important;color:#1c1c1e !important}
.btn-select.active{background:#007aff !important;color:#fff !important}
/* ── Modo selección ── */
body.select-mode .card{user-select:none}
body.select-mode .card:hover{background:#f0f6ff}
.card-check{display:none;width:20px;height:20px;border-radius:50%;border:2px solid #c7c7cc;flex-shrink:0;align-self:center;transition:all .15s}
body.select-mode .card-check{display:flex;align-items:center;justify-content:center}
.card.selected .card-check{background:#007aff;border-color:#007aff}
.card.selected .card-check::after{content:"✓";color:#fff;font-size:11px;font-weight:700}
.card.selected{background:#f0f6ff}
/* ── Barra inferior guardar ── */
.save-bar{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #e5e5ea;padding:12px 20px;display:none;align-items:center;justify-content:space-between;gap:12px;z-index:20;box-shadow:0 -2px 12px rgba(0,0,0,.08)}
.save-bar.visible{display:flex}
.save-bar-text{font-size:14px;color:#3a3a3c;font-weight:500}
.btn-save{background:#007aff;color:#fff;padding:10px 20px;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer}
.btn-save:disabled{opacity:.5;cursor:default}
/* ── Toast ── */
.toast{position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#1c1c1e;color:#fff;padding:10px 20px;border-radius:10px;font-size:14px;font-weight:500;opacity:0;transition:opacity .25s;pointer-events:none;z-index:100;white-space:nowrap}
.toast.show{opacity:1}
</style>"""

# ─── UI: HEADER ───────────────────────────────────────────────────────────────
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
</div>
<div class="save-bar" id="save-bar">
  <span class="save-bar-text" id="save-bar-text">0 noticias seleccionadas</span>
  <button class="btn-save" id="btn-save" onclick="saveToBoard()" disabled>Guardar en tablero →</button>
</div>
<div class="toast" id="toast"></div>"""

# ─── UI: JAVASCRIPT COMPLETO ──────────────────────────────────────────────────
COMPLETE_JS = """<script>
/* ── Añadir card-check a todas las cards que no lo tengan ── */
document.querySelectorAll('.card').forEach(function(card) {
  if (!card.querySelector('.card-check')) {
    var chk = document.createElement('div');
    chk.className = 'card-check';
    card.appendChild(chk);
  }
});

/* ── Selección de cards (fase de captura para interceptar el <a> href) ── */
document.addEventListener('click', function(e) {
  var card = e.target.closest('.card');
  if (!card || !document.body.classList.contains('select-mode')) return;
  e.preventDefault();
  card.classList.toggle('selected');
  updateSaveBar();
}, true);

function updateSaveBar() {
  var n   = document.querySelectorAll('.card.selected').length;
  var txt = document.getElementById('save-bar-text');
  var btn = document.getElementById('btn-save');
  var bar = document.getElementById('save-bar');
  if (txt) txt.textContent = n + (n === 1 ? ' noticia seleccionada' : ' noticias seleccionadas');
  if (btn) btn.disabled = n === 0;
  if (bar) bar.classList.toggle('visible', n > 0);
}

function toggleSelect() {
  var active = document.body.classList.toggle('select-mode');
  var btn = document.getElementById('btn-select');
  if (btn) btn.classList.toggle('active', active);
  if (!active) {
    document.querySelectorAll('.card.selected').forEach(function(c) { c.classList.remove('selected'); });
    updateSaveBar();
  }
}

function saveToBoard() {
  var items = [];
  document.querySelectorAll('.card.selected').forEach(function(card) {
    items.push({
      title:  (card.querySelector('.card-title')  || {}).textContent || '',
      url:    card.href || '',
      source: (card.querySelector('.card-source') || {}).textContent || '',
      date:   (card.querySelector('.card-date')   || {}).textContent || '',
      saved:  new Date().toISOString(),
    });
  });
  var board = JSON.parse(localStorage.getItem('digestBoard') || '[]');
  board = items.concat(board);
  localStorage.setItem('digestBoard', JSON.stringify(board));
  showToast(items.length + (items.length === 1 ? ' noticia guardada' : ' noticias guardadas'));
  document.body.classList.remove('select-mode');
  var btn = document.getElementById('btn-select');
  if (btn) btn.classList.remove('active');
  document.querySelectorAll('.card.selected').forEach(function(c) { c.classList.remove('selected'); });
  updateSaveBar();
}

function triggerUpdate() {
  var btn = document.getElementById('update-btn');
  if (btn) { btn.disabled = true; btn.textContent = '↻ Actualizando…'; }
  fetch('https://api.github.com/repos/morenopascual/streaming-digest/actions/workflows/update-digest.yml/dispatches', {
    method: 'POST',
    headers: { 'Accept': 'application/vnd.github.v3+json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: 'main' }),
  }).then(function() {
    showToast('Actualización iniciada — lista en ~2 min');
  }).catch(function() {
    showToast('Recarga la página para ver novedades');
  }).finally(function() {
    setTimeout(function() {
      if (btn) { btn.disabled = false; btn.textContent = '↻ Actualizar'; }
    }, 4000);
  });
}

function showToast(msg) {
  var t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function() { t.classList.remove('show'); }, 2500);
}
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
    articles = articles[:MAX_ARTICLES]
    print(f"  → {len(articles)} artículos enviados a Claude (máx. {MAX_ARTICLES})")
    return articles

# ─── GENERATE ─────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Eres un editor especializado en el sector del streaming, VOD y publicidad digital.
Tu tarea es generar el HTML del digest diario de Atresmedia a partir de artículos en JSON.
Devuelves ÚNICAMENTE el HTML, sin markdown, sin ``` ni explicaciones."""

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

REGLAS IMPORTANTES:
- Genera SOLO desde <!DOCTYPE html> hasta </html>
- Incluye el bloque <style> completo del template (copiarlo tal cual)
- NO incluyas <div class="site-header">, save-bar, toast, ni ningún <script> — el sistema los añade automáticamente
- Excluye Disney NO relacionado con Disney+ (cine, parques, Marvel, Star Wars)
- Excluye menciones a Max Verstappen
- Omite categorías sin artículos
- El análisis final incluye "Temas del día" (4-5 puntos) y "Para seguir" (2-3 tendencias para Atresmedia/atresplayer)

Template de referencia (usa el mismo CSS y estructura de cards):
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
def inject_extra_css(html):
    """Añade el CSS interactivo justo antes de </head>."""
    if "</head>" in html:
        return html.replace("</head>", EXTRA_CSS + "\n</head>", 1)
    return html

def inject_header(html, date):
    """Elimina cualquier site-header que Claude haya generado e inyecta
    el canónico (con save-bar y toast) justo después de <body>."""
    header = HEADER_HTML.format(date=date)
    # Eliminar site-header existente si lo hay
    html = re.sub(
        r'<div class=["\']site-header["\']>[\s\S]*?</div>\s*</div>',
        '', html, count=1
    )
    # Inyectar después de <body>
    if "<body>" in html:
        return html.replace("<body>", "<body>\n" + header, 1)
    return html

def inject_js(html):
    """Elimina cualquier <script> existente e inyecta el JS completo antes de </body>.
    Busca </body> o </html> como fallback para garantizar la inyección."""
    html = re.sub(r'<script[\s\S]*?</script>', '', html)
    if "</body>" in html:
        return html.replace("</body>", COMPLETE_JS + "\n</body>", 1)
    if "</html>" in html:
        return html.replace("</html>", COMPLETE_JS + "\n</html>", 1)
    return html + "\n" + COMPLETE_JS

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

    # Post-procesado determinista: CSS + header + JS siempre correctos
    html = inject_extra_css(html)
    html = inject_header(html, today)
    html = inject_js(html)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✓  index.html actualizado")

if __name__ == "__main__":
    main()
