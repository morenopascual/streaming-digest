#!/usr/bin/env python3
"""
Genera index.html a partir de digest.json usando la API de Claude.
Se ejecuta en GitHub Actions tras fetch_digest.py.

Requiere:
  - ANTHROPIC_API_KEY  (GitHub secret)
  - GITHUB_TOKEN       (disponible automáticamente en Actions)
  - GITHUB_REPOSITORY  (disponible automáticamente en Actions)
"""

import json, os, base64, sys
from datetime import datetime
from urllib.parse import urlparse

import anthropic
import requests

# ─── CONFIG ──────────────────────────────────────────────────────────────────

SECTION_COLORS = {
    "PLATAFORMAS Y SECTOR": "#2980b9",
    "IA":                   "#7b68ee",
    "CTV":                  "#1a9e75",
    "REDES SOCIALES":       "#e6a817",
    "MEDIOS Y TELEVISIÓN":  "#d84040",
    "REGULACIÓN":           "#e67e22",
    "FABRICANTES":          "#555555",
    "PUBLICIDAD":           "#e91e8c",
    "ESTUDIOS E INFORMES":  "#16a085",
}

CLAUDE_MODEL = "claude-opus-4-6"

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def section_color(epigrafe):
    return SECTION_COLORS.get(epigrafe.upper(), "#888888")

def short_url(url):
    try:
        p = urlparse(url)
        path = p.path[:36] + "…" if len(p.path) > 36 else p.path
        return p.netloc.replace("www.", "") + path
    except Exception:
        return url[:55]

# ─── STEP 1: LOAD DIGEST ─────────────────────────────────────────────────────

def load_digest():
    with open("digest.json", "r", encoding="utf-8") as f:
        return json.load(f)

# ─── STEP 2: PROCESS WITH CLAUDE ─────────────────────────────────────────────

PROMPT_TEMPLATE = """Eres el editor de un digest diario de noticias sobre streaming, VOD y publicidad digital para Atresmedia (grupo audiovisual español).

Fecha del digest: {date}

Tienes los siguientes artículos de diversas fuentes internacionales:

{articles_json}

Tu tarea es:

1. FILTRAR: Elimina artículos que sean puramente contenido editorial sin valor estratégico (sinopsis de episodios, entrevistas a actores sobre su personaje, listas de estrenos, noticias de famosos sin impacto en la industria). Mantén únicamente lo que sea relevante para alguien que trabaja en estrategia de streaming, publicidad digital o gestión de medios audiovisuales.

2. AGRUPAR: Si varios artículos cubren la misma noticia o tema (por ejemplo, dos medios distintos que informan de lo mismo), agrúpalos bajo un único titular.

3. TITULAR EN ESPAÑOL: Escribe un titular en español periodístico y preciso para cada grupo (no traducción literal, sino adaptación editorial de calidad). Haz lo mismo para cada artículo individual.

4. ORGANIZAR en secciones. Usa solo las que tengan contenido relevante:
   - PLATAFORMAS Y SECTOR
   - IA
   - CTV
   - REDES SOCIALES
   - MEDIOS Y TELEVISIÓN
   - REGULACIÓN
   - FABRICANTES
   - PUBLICIDAD
   - ESTUDIOS E INFORMES

Devuelve ÚNICAMENTE un bloque JSON válido (sin texto antes ni después, sin markdown):
{{
  "date": "{date}",
  "sections": [
    {{
      "epigrafe": "NOMBRE SECCIÓN",
      "groups": [
        {{
          "titular": "Titular del grupo en español",
          "articles": [
            {{
              "title_es": "Titular del artículo en español",
              "source": "Nombre del medio",
              "url": "https://..."
            }}
          ]
        }}
      ]
    }}
  ],
  "analisis": {{
    "temas_del_dia": "Tema 1 · Tema 2 · Tema 3 · Tema 4 · Tema 5",
    "para_seguir": "① Punto 1 con contexto. ② Punto 2 con contexto. ③ Punto 3 con contexto."
  }}
}}"""

def process_with_claude(digest):
    # Build a lookup: url -> published date
    url_to_published = {}
    articles = []
    for src in digest.get("sources", []):
        for art in src.get("articles", []):
            url_to_published[art["url"]] = art.get("published", "")
            articles.append({
                "title":     art["title"],
                "url":       art["url"],
                "source":    art["source"],
                "published": art.get("published", ""),
            })

    if not articles:
        print("Sin artículos para procesar.")
        sys.exit(0)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = PROMPT_TEMPLATE.format(
        date=digest.get("date", ""),
        articles_json=json.dumps(articles, ensure_ascii=False, indent=2),
    )

    print(f"  Enviando {len(articles)} artículos a Claude ({CLAUDE_MODEL})…")
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    processed = json.loads(raw)
    # Attach published dates from original digest (Claude may not preserve them)
    for sec in processed.get("sections", []):
        for group in sec.get("groups", []):
            for art in group.get("articles", []):
                if not art.get("published"):
                    art["published"] = url_to_published.get(art.get("url", ""), "")
    return processed

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def fmt_date(raw):
    """Format date string as 'DD MMM' in Spanish. Handles DD/MM/YYYY HH:MM UTC and ISO."""
    if not raw:
        return ""
    MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
    # Format: "28/05/2026 02:44 UTC"
    try:
        part = raw.split(" ")[0]  # "28/05/2026"
        d, m, y = part.split("/")
        return f"{int(d)} {MESES[int(m)-1]}"
    except Exception:
        pass
    # ISO: "2026-05-28T..."
    try:
        dt = datetime.fromisoformat(raw[:10])
        return f"{dt.day} {MESES[dt.month-1]}"
    except Exception:
        pass
    return ""

# ─── STEP 3: GENERATE HTML ───────────────────────────────────────────────────

def build_cards(sections):
    html = ""
    for sec in sections:
        epigrafe = sec["epigrafe"]
        color    = section_color(epigrafe)
        html += f'<div class="section">\n'
        html += f'<div class="section-label" style="color:{color}">{epigrafe}</div>\n'
        for group in sec.get("groups", []):
            html += '<div class="group">\n'
            html += f'<div class="group-title" style="border-left:3px solid {color}">{group["titular"]}</div>\n'
            for art in group.get("articles", []):
                url     = art.get("url", "#")
                title   = art.get("title_es", "")
                source  = art.get("source", "")
                pub     = fmt_date(art.get("published", ""))
                surl    = short_url(url)
                date_html = f'<span class="card-sep">·</span><span class="card-date">{pub}</span>' if pub else ""
                html += f'''<a class="card" href="{url}" target="_blank" rel="noopener">
  <div class="card-accent" style="background:{color}"></div>
  <div class="card-body">
    <div class="card-title">{title}</div>
    <div class="card-meta">
      <span class="card-source">{source}</span>
      {date_html}
      <span class="card-sep">·</span>
      <span class="card-url">{surl}</span>
      <span class="card-ext">↗</span>
    </div>
  </div>
</a>\n'''
            html += '</div>\n'
        html += '</div>\n'
    return html

def build_analysis(analisis):
    if not analisis:
        return ""
    return f'''<div class="section">
  <div class="section-label">Análisis del día</div>
  <div class="analysis">
    <div class="analysis-header">Análisis del día</div>
    <div class="analysis-row">
      <div class="analysis-label">Temas del día</div>
      <div class="analysis-text">{analisis.get("temas_del_dia","")}</div>
    </div>
    <div class="analysis-row">
      <div class="analysis-label">Para seguir</div>
      <div class="analysis-text">{analisis.get("para_seguir","")}</div>
    </div>
  </div>
</div>\n'''

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Digest Streaming &amp; VOD — Atresmedia</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;background:#f2f2f7;color:#1c1c1e;font-size:16px}}
a{{color:inherit;text-decoration:none}}
.site-header{{background:#fff;border-bottom:1px solid #e5e5ea;padding:16px 20px;position:sticky;top:0;z-index:10}}
.site-header h1{{font-size:19px;font-weight:700;letter-spacing:-.2px}}
.site-header p{{font-size:13px;color:#8e8e93;margin-top:3px}}
.container{{max-width:680px;margin:0 auto;padding:16px 0 52px}}
.section{{margin-bottom:28px}}
.section-label{{font-size:12px;font-weight:700;letter-spacing:.09em;color:#8e8e93;text-transform:uppercase;padding:0 16px 8px}}
.group{{background:#fff;border-radius:12px;overflow:hidden;margin:0 12px 10px;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.group-title{{font-size:14px;font-weight:600;color:#1c1c1e;padding:13px 15px 11px;border-bottom:1px solid #f2f2f7;line-height:1.4;background:#fafafa;border-left-width:3px;border-left-style:solid}}
.card{{display:flex;align-items:flex-start;gap:12px;padding:13px 15px;border-bottom:1px solid #f2f2f7;cursor:pointer;transition:background .1s}}
.card:last-child{{border-bottom:none}}
.card:hover{{background:#f9f9f9}}
.card-accent{{width:3px;min-height:44px;border-radius:2px;flex-shrink:0;margin-top:2px}}
.card-body{{flex:1;min-width:0}}
.card-title{{font-size:15px;font-weight:500;line-height:1.45;color:#1c1c1e;margin-bottom:6px}}
.card-meta{{display:flex;align-items:center;gap:5px;overflow:hidden}}
.card-source{{font-size:12px;font-weight:600;color:#8e8e93;flex-shrink:0}}
.card-sep{{font-size:10px;color:#c7c7cc;flex-shrink:0}}
.card-url{{font-size:12px;color:#c7c7cc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.card-date{{font-size:12px;color:#aaaaaa;flex-shrink:0}}
.card-ext{{font-size:12px;color:#007aff;margin-left:auto;flex-shrink:0;padding-left:8px}}
.analysis{{background:#fff;border-radius:12px;margin:0 12px;box-shadow:0 1px 3px rgba(0,0,0,.07);overflow:hidden}}
.analysis-header{{background:#1c1c1e;color:#fff;padding:12px 15px;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}}
.analysis-row{{padding:13px 15px;border-bottom:1px solid #f2f2f7}}
.analysis-row:last-child{{border-bottom:none}}
.analysis-label{{font-size:12px;font-weight:700;color:#007aff;text-transform:uppercase;letter-spacing:.04em;margin-bottom:5px}}
.analysis-text{{font-size:14px;color:#3a3a3c;line-height:1.6}}
.site-footer{{text-align:center;padding:20px;font-size:12px;color:#c7c7cc}}
</style>
</head>
<body>
<div class="site-header">
  <h1>Digest Streaming &amp; VOD</h1>
  <p>{date} &nbsp;·&nbsp; Atresmedia</p>
</div>
<div class="container">
{body}
</div>
<div class="site-footer">Generado automáticamente · {date} · Atresmedia</div>
</body>
</html>"""

def generate_html(processed):
    body = build_cards(processed.get("sections", []))
    body += build_analysis(processed.get("analisis", {}))
    return HTML_TEMPLATE.format(date=processed.get("date", ""), body=body)

# ─── STEP 4: COMMIT TO GITHUB ────────────────────────────────────────────────

def commit_html(html_content):
    token = os.environ.get("GITHUB_TOKEN")
    repo  = os.environ.get("GITHUB_REPOSITORY", "morenopascual/streaming-digest")

    if not token:
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("  (sin GITHUB_TOKEN) HTML guardado como index.html local.")
        return

    url     = f"https://api.github.com/repos/{repo}/contents/index.html"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

    r   = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {
        "message": f"digest html: {datetime.now().strftime('%Y-%m-%d')}",
        "content": base64.b64encode(html_content.encode("utf-8")).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code in (200, 201):
        print(f"  ✓ Publicado en https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/")
    else:
        print(f"  ✗ Error {resp.status_code}: {resp.text}")
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html_content)

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    print("1/4 Cargando digest.json…")
    digest = load_digest()

    print("2/4 Procesando con Claude API…")
    processed = process_with_claude(digest)

    with open("digest_processed.json", "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)
    print("    digest_processed.json guardado.")

    print("3/4 Generando HTML…")
    html = generate_html(processed)

    print("4/4 Publicando en GitHub…")
    commit_html(html)

    print("¡Completado!")

if __name__ == "__main__":
    main()
