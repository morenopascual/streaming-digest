#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
fetch_digest.py
Digest RSS para Ac2ality sin IA ni Anthropic.

Qué hace:
  1. Descarga feeds RSS.
  2. Filtra noticias recientes por keywords editoriales.
  3. Clasifica cada noticia por categoría.
  4. Calcula un score simple de relevancia.
  5. Marca noticias sensibles, pero no las elimina automáticamente.
  6. Deduplica artículos por URL y título.
  7. Guarda digest.json para que index.html lo pueda leer directamente.

Ejecutar manualmente:
  python fetch_digest.py

Dependencia:
  pip install feedparser

Uso recomendado en GitHub Actions:
  python fetch_digest.py
  git add digest.json
  git commit / push
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
import os
import re
import ssl
import sys
import tempfile
import threading
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
import socket
import urllib.request
from urllib.error import URLError
from urllib.parse import urlparse, urlunparse

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

import feedparser


# ─────────────────────────────────────────────
# 0. CONFIGURACIÓN GENERAL
# ─────────────────────────────────────────────

PROJECT_NAME = "ac2ality-news-digest"
OUTPUT_FILE = "digest.json"

WINDOW_HOURS = 12
MAX_TOTAL_ARTICLES = 250
MAX_ARTICLES_PER_SOURCE = 30

# Si una noticia no tiene fecha en el RSS, se puede incluir.
# En RSS reales hay fuentes que no informan bien la fecha.
INCLUDE_UNDATED_ARTICLES = True

# Score mínimo para incluir una noticia.
# Lo normal: 2 o 3.
MIN_SCORE = 3

USER_AGENT = "Mozilla/5.0 (compatible; Ac2alityDigestBot/1.0)"
FEED_TIMEOUT_SECONDS = 15

if ZoneInfo:
    LOCAL_TZ = ZoneInfo("Europe/Madrid")
else:
    LOCAL_TZ = timezone.utc

# ─────────────────────────────────────────────
# 1. FUENTES RSS
# ─────────────────────────────────────────────
# Nota práctica:
# - Mantengo prioridad a RSS/Atom oficiales cuando existen.
# - Uso Google News RSS solo como fallback de descubrimiento.
# - Para AC2ALITY, los feeds ALT de sucesos/viral sirven para detectar y revisar,
#   no para publicar automáticamente.

FEEDS = [
    ("20 Minutos", "https://www.20minutos.es/rss/"), 
    ("20 Minutos España", "https://www.20minutos.es/rss/nacional/"),  
    ("20 Minutos Madrid", "https://www.20minutos.es/rss/madrid/"),  

    ("El País Últimas", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/ultimas-noticias/portada"),
    ("El País España", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/espana/portada"),
    ("El País Sociedad", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/sociedad/portada"),
    ("El País Economía", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/economia/portada"),

    ("La Vanguardia Portada", "https://www.lavanguardia.com/rss/home.xml"),  
    ("La Vanguardia Sociedad", "https://www.lavanguardia.com/rss/vida.xml"),  
    ("La Vanguardia Gente", "https://www.lavanguardia.com/rss/gente.xml"), 
     
    ("OKDiario Portada", "https://okdiario.com/feed"),
    ("OKDiario España", "https://okdiario.com/espana/feed"),
    ("OKDiario Sociedad", "https://okdiario.com/sociedad/feed"),
    ("OKDiario Sucesos", "https://okdiario.com/sucesos/feed"),
    ("OKDiario Internacional", "https://okdiario.com/internacional/feed"),

    ("elDiario.es", "https://www.eldiario.es/rss/"),  

    ("Antena 3 Últimas", "https://news.google.com/rss/search?q=site:antena3.com/noticias/ultimas-noticias+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("Antena 3 España", "https://news.google.com/rss/search?q=site:antena3.com/noticias/espana+when:2d&hl=es&gl=ES&ceid=ES:es"),

    ("Europa Press", "https://news.google.com/rss/search?q=site:europapress.es+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("EFE", "https://news.google.com/rss/search?q=site:efe.com+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("EFE Verifica", "https://news.google.com/rss/search?q=site:efe.com+efe+verifica+when:7d&hl=es&gl=ES&ceid=ES:es"),

    ("Telecinco Noticias", "https://news.google.com/rss/search?q=site:telecinco.es/noticias+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("Telecinco Sociedad", "https://news.google.com/rss/search?q=site:telecinco.es/noticias/sociedad+when:2d&hl=es&gl=ES&ceid=ES:es"),

    ("Antena 3 Sociedad", "https://news.google.com/rss/search?q=site:antena3.com/noticias/sociedad+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("La Sexta Noticias", "https://news.google.com/rss/search?q=site:lasexta.com/noticias+when:2d&hl=es&gl=ES&ceid=ES:es"),

    ("El Mundo", "https://news.google.com/rss/search?q=site:elmundo.es+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("ABC", "https://news.google.com/rss/search?q=site:abc.es+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("El Español", "https://news.google.com/rss/search?q=site:elespanol.com+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("La Razón", "https://news.google.com/rss/search?q=site:larazon.es+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("Telemadrid", "https://news.google.com/rss/search?q=site:telemadrid.es+when:2d&hl=es&gl=ES&ceid=ES:es"),

    ("La Vanguardia Sucesos", "https://www.lavanguardia.com/rss/sucesos.xml"),  

    ("BBC Mundo", "https://feeds.bbci.co.uk/mundo/rss.xml"),
    ("France 24 Español", "https://www.france24.com/es/rss"),
    ("DW Español", "https://rss.dw.com/rdf/rss-sp-all"),
    ("Euronews Español", "https://es.euronews.com/rss"),
    ("El País Internacional", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada"),
    ("La Vanguardia Internacional", "https://www.lavanguardia.com/rss/internacional.xml"),  
    ("Antena 3 Mundo", "https://news.google.com/rss/search?q=site:antena3.com/noticias/mundo+when:2d&hl=es&gl=ES&ceid=ES:es"),

    ("The Guardian World", "https://www.theguardian.com/world/rss"),
    ("Washington Post World", "https://feeds.washingtonpost.com/rss/world"),
    ("Reuters World", "https://news.google.com/rss/search?q=site:reuters.com/world+when:2d&hl=en-GB&gl=GB&ceid=GB:en"),
    ("AP News", "https://news.google.com/rss/search?q=site:apnews.com+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("New York Times World", "https://news.google.com/rss/search?q=site:nytimes.com/section/world+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("CNN World", "https://news.google.com/rss/search?q=site:cnn.com/world+when:2d&hl=en-US&gl=US&ceid=US:en"),

    ("AS Portada", "https://feeds.as.com/mrss-s/pages/as/site/as.com/portada"),  
    ("El País Deportes", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/deportes/portada"),
    ("Marca", "https://e00-marca.uecdn.es/rss/portada.xml"),  
    ("Mundo Deportivo", "https://www.mundodeportivo.com/rss/home.xml"),  
    ("Sport", "https://news.google.com/rss/search?q=site:sport.es+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("Antena 3 Deportes", "https://news.google.com/rss/search?q=site:antena3.com/noticias/deportes+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("OKDiario Deportes", "https://okdiario.com/deportes/feed"),
    ("OKDiario Fútbol", "https://okdiario.com/deportes/futbol/feed"),


    ("El País Televisión", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/television/portada"),
    ("El País Gente", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/gente/portada"),

    ("Vertele", "https://news.google.com/rss/search?q=site:vertele.eldiario.es+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("Diez Minutos", "https://news.google.com/rss/search?q=site:diezminutos.es+when:2d&hl=es&gl=ES&ceid=ES:es"),
    ("FórmulaTV", "https://news.google.com/rss/search?q=site:formulatv.com+when:2d&hl=es&gl=ES&ceid=ES:es"),

    ("Xataka", "https://www.xataka.com/feedburner.xml"),
    ("Xataka Ciencia", "https://www.xatakaciencia.com/feedburner.xml"),
    ("Genbeta", "https://www.genbeta.com/feedburner.xml"),
    ("Hipertextual", "https://hipertextual.com/feed"),

    ("El País Tecnología", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia/portada"),
    ("La Vanguardia Tecnología", "https://www.lavanguardia.com/rss/tecnologia.xml"),  


    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ("Wired", "https://www.wired.com/feed/rss"),

    ("El País Ciencia", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/ciencia/portada"),
    ("OKDiario Ciencia", "https://okdiario.com/ciencia/feed"),

    ("OKDiario Cool Actualidad", "https://okdiario.com/cool/actualidad/feed"),
    ("OKDiario Famosos", "https://okdiario.com/noticias/famosos/feed"),
    ("OKDiario Redes Sociales", "https://okdiario.com/redes-sociales/feed"),
]


# ─────────────────────────────────────────────
# 2. CATEGORÍAS EDITORIALES AC2ALITY
# ─────────────────────────────────────────────
# Cada artículo se clasifica en la categoría con más coincidencias.
#
# Taxonomía adaptada a AC2ALITY:
# - Keywords estables, no dependientes de famosos, películas o casos concretos.
# - Diseñada para detectar patrones de actualidad: sucesos, sociedad, mundo,
#   deporte, cultura pop, tecnología, salud, educación, consumo y virales.
# - Evita nombres propios coyunturales tipo artista/película/caso de la semana.

CATEGORIES = {
    "SUCESOS": [
        # Delitos / investigación
        "sucesos", "crimen", "delito", "delincuencia", "investigación",
        "investigan", "investigado", "investigada", "detenido", "detenida",
        "detenidos", "arrestado", "arrestada", "sospechoso", "sospechosa",
        "acusado", "acusada", "imputado", "imputada",

        # Violencia / muertes / desapariciones
        "asesinato", "homicidio", "muerte", "muere", "fallece", "fallecido",
        "cadáver", "desaparecido", "desaparecida", "desaparición",
        "tiroteo", "apuñalamiento", "arma blanca", "arma de fuego",
        "agresión", "agresión sexual", "violación", "abuso", "maltrato",
        "violencia machista", "violencia de género", "violencia doméstica",
        "secuestro", "trata", "tráfico de personas",

        # Justicia / cuerpos de seguridad
        "policía", "guardia civil", "mossos", "ertzaintza", "policía nacional",
        "policía local", "tribunal", "juzgado", "juez", "fiscalía",
        "fiscal", "juicio", "condena", "condenado", "condenada",
        "sentencia", "prisión", "cárcel", "libertad provisional",

        # Accidentes / emergencias
        "accidente", "atropello", "incendio", "explosión", "derrumbe",
        "rescate", "emergencia", "heridos", "víctimas",
    ],

    "SOCIEDAD": [
        # Vida cotidiana / ciudadanía
        "sociedad", "ciudadanos", "vecinos", "barrio", "ciudad", "municipio",
        "comunidad", "convivencia", "familia", "familias", "infancia",
        "mayores", "jóvenes", "adolescentes", "generación z",

        # Vivienda / trabajo / economía doméstica
        "vivienda", "alquiler", "hipoteca", "desahucio", "empleo", "trabajo",
        "paro", "salarios", "sueldo", "conciliación", "jornada laboral",

        # Servicios públicos / transporte / ciudad
        "transporte", "metro", "renfe", "cercanías", "autobús", "movilidad",
        "tráfico", "carretera", "agua", "luz", "gas", "sanidad pública",
        "servicios públicos",

        # Derechos / convivencia / movimientos sociales
        "igualdad", "derechos", "discapacidad", "inclusión", "solidaridad",
        "voluntariado", "manifestación", "protesta", "huelga",
        "discriminación", "racismo", "xenofobia", "lgtbi",

        # Animales / vida urbana
        "mascotas", "animal", "animales", "maltrato animal",
        "abandono animal",
    ],

    "POLÍTICA / LEYES": [
        # Instituciones
        "gobierno", "congreso", "senado", "ministerio", "ministro",
        "ministra", "presidente del gobierno", "presidenta", "alcalde",
        "alcaldesa", "comunidad autónoma", "ayuntamiento",

        # Normativa / regulación
        "ley", "decreto", "reforma", "normativa", "regulación", "regulador",
        "boe", "aprobado", "aprueba", "entra en vigor", "prohibición",
        "obligatorio", "permiso", "licencia", "sanción", "multa",

        # Justicia política / instituciones
        "tribunal constitucional", "tribunal supremo", "audiencia nacional",
        "fiscalía", "juez", "sentencia", "recurso", "investidura",
        "comisión", "comparecencia", "votación", "pacto",

        # Partidos / elecciones de forma genérica
        "elecciones", "campaña electoral", "sondeo", "encuesta electoral",
        "partido político", "oposición", "coalición", "parlamento",
        "unión europea", "comisión europea", "bruselas",
    ],

    "MUNDO": [
        # Actualidad internacional general
        "mundo", "internacional", "exterior", "global", "europa",
        "unión europea", "estados unidos", "américa latina", "latinoamérica",
        "áfrica", "asia", "oriente medio",

        # Conflictos / seguridad / diplomacia
        "guerra", "conflicto", "ataque", "bombardeo", "invasión",
        "alto el fuego", "frontera", "tensión", "crisis diplomática",
        "sanciones internacionales", "ejército", "militar", "otan",
        "onu", "naciones unidas", "embajada",

        # Migración / derechos humanos
        "migración", "migrantes", "refugiados", "asilo", "frontera",
        "derechos humanos", "crisis humanitaria",

        # Catástrofes / sucesos internacionales
        "terremoto", "huracán", "inundaciones", "incendio forestal",
        "catástrofe", "emergencia internacional", "epidemia",
    ],

    "DEPORTES": [
        # Deporte general
        "deporte", "deportes", "deportista", "atleta", "selección",
        "campeón", "campeona", "campeonato", "torneo", "final",
        "semifinal", "récord", "medalla", "lesión", "sanción deportiva",

        # Fútbol
        "fútbol", "liga", "champions", "mundial", "eurocopa",
        "copa del mundo", "club", "equipo", "fichaje", "traspaso",
        "entrenador", "presidente del club", "estadio", "afición",
        "árbitro", "var",

        # Otros deportes con potencial AC2ALITY
        "tenis", "baloncesto", "nba", "euroliga", "ufc", "mma",
        "boxeo", "fórmula 1", "motogp", "atletismo", "maratón",
        "juegos olímpicos", "deporte femenino", "pádel",
    ],

    "CULTURA POP": [
        # Música / conciertos / festivales
        "entretenimiento", "cultura pop", "música", "cantante", "artista",
        "grupo musical", "banda", "concierto", "gira", "tour", "festival",
        "álbum", "canción", "single", "videoclip", "entradas", "sold out",
        "estadio", "premios musicales",

        # Cine / series / televisión
        "cine", "película", "estreno", "tráiler", "secuela", "precuela",
        "taquilla", "premios de cine", "serie", "temporada", "plataforma",
        "streaming", "televisión", "programa", "presentador", "presentadora",
        "audiencia", "reality", "talent show",

        # Famosos / figuras públicas / influencers
        "famoso", "famosa", "celebridad", "figura pública", "actor",
        "actriz", "influencer", "tiktoker", "youtuber", "streamer",
        "creador de contenido", "creadora de contenido", "alfombra roja",
        "premios", "boda", "ruptura", "polémica", "declaraciones",

        # Realeza / instituciones simbólicas
        "realeza", "casa real", "rey", "reina", "princesa", "príncipe",
        "papa", "vaticano",
    ],

    "TECNOLOGÍA E IA": [
        # IA / software / plataformas
        "tecnología", "inteligencia artificial", "ia", "ai", "ia generativa",
        "chatbot", "asistente virtual", "modelo de lenguaje", "algoritmo",
        "automatización", "deepfake", "imagen generada", "vídeo generado",
        "app", "aplicación", "plataforma digital", "red social",

        # Big tech / internet / regulación digital
        "big tech", "empresa tecnológica", "startup", "datos", "privacidad",
        "protección de datos", "ciberseguridad", "hackeo", "hacker",
        "ciberataque", "estafa online", "phishing", "fraude digital",
        "contraseña", "filtración de datos", "desinformación",

        # Gadgets / movilidad / espacio
        "móvil", "smartphone", "ordenador", "gadget", "robot", "robótica",
        "coche eléctrico", "vehículo eléctrico", "batería", "cohete",
        "misión espacial", "satélite", "exploración espacial",

        # Tecnología aplicada
        "tecnología médica", "tecnología educativa", "drones",
        "realidad virtual", "realidad aumentada", "criptomonedas",
        "blockchain",
    ],

    "CIENCIA Y SALUD": [
        # Ciencia / investigación
        "ciencia", "científico", "científica", "investigación", "estudio",
        "descubrimiento", "hallazgo", "ensayo", "ensayo clínico",
        "laboratorio", "universidad", "investigadores", "paper",
        "revista científica",

        # Salud / medicina
        "salud", "salud pública", "hospital", "médico", "médica",
        "medicina", "paciente", "tratamiento", "terapia", "vacuna",
        "diagnóstico", "prevención", "cirugía", "trasplante",
        "urgencias", "atención primaria",

        # Enfermedades / brotes
        "enfermedad", "virus", "bacteria", "infección", "brote",
        "epidemia", "pandemia", "cáncer", "tumor", "corazón",
        "infarto", "ictus", "alzheimer", "salud mental", "ansiedad",
        "depresión", "adicción", "drogas", "cocaína",
    ],

    "CONSUMO / ECONOMÍA": [
        # Economía cotidiana
        "economía", "consumo", "consumidores", "precio", "precios",
        "inflación", "subida de precios", "rebaja", "coste de vida",
        "factura", "alquiler", "hipoteca", "supermercado", "gasolina",
        "electricidad", "ahorro",

        # Empresas / marcas / plataformas
        "empresa", "compañía", "marca", "marcas", "negocio", "beneficio",
        "ingresos", "pérdidas", "ventas", "mercado", "ecommerce",
        "comercio electrónico", "tienda online", "plataforma", "suscripción",

        # Regulación / multas / fraudes
        "multa", "sanción", "fraude", "estafa", "publicidad engañosa",
        "competencia", "consumo multa", "retirada del mercado",
        "producto defectuoso", "alerta de consumo",

        # Dinero / inversión / empleo
        "millones de euros", "inversión", "inversor", "bolsa",
        "salario", "empleo", "despidos", "huelga", "acuerdo laboral",
    ],

    "EDUCACIÓN": [
        # Sistema educativo
        "educación", "colegio", "instituto", "escuela", "universidad",
        "campus", "fp", "formación profesional", "bachillerato",
        "guardería", "aula", "clase",

        # Pruebas / becas / acceso
        "selectividad", "ebau", "pau", "examen", "nota de corte",
        "matrícula", "beca", "becas", "admisión", "plaza universitaria",

        # Conflictos / convivencia escolar
        "acoso escolar", "bullying", "convivencia escolar", "absentismo",
        "uso del móvil", "móvil en clase",
    ],

    "MEDIO AMBIENTE / CLIMA": [
        # Clima / fenómenos extremos
        "medio ambiente", "clima", "cambio climático", "calor extremo",
        "ola de calor", "sequía", "lluvias", "inundaciones", "dana",
        "temporal", "incendio forestal", "contaminación", "calidad del aire",

        # Naturaleza / biodiversidad
        "biodiversidad", "ecosistema", "océano", "mar", "playa",
        "especie protegida", "animales", "fauna", "residuos", "plástico",

        # Energía / sostenibilidad
        "sostenibilidad", "energía renovable", "renovables", "emisiones",
        "co2", "reciclaje", "transición energética", "vehículo eléctrico",
    ],
}


# Lista plana de keywords relevantes.
# Se genera automáticamente desde CATEGORIES, pero se pueden añadir extras.
#
# Las EXTRA_KEYWORDS no deben depender de nombres propios del momento.
# Deben capturar formatos editoriales, señales de actualidad y lenguaje típico
# de piezas explicativas o virales.

EXTRA_KEYWORDS = [
    # Marca / enfoque editorial
    "ac2ality",
    "actualidad",
    "noticias de hoy",
    "5 noticias de hoy",
    "5 cosas de hoy",
    "resumen del día",
    "lo más importante",
    "lo que se sabe",
    "qué ha pasado",
    "por qué importa",
    "claves",
    "cronología",
    "contexto",
    "explicado",
    "explicada",

    # Señales de urgencia / desarrollo
    "última hora",
    "en directo",
    "actualización",
    "nuevo dato",
    "nuevos detalles",
    "investigan",
    "confirmado",
    "según fuentes",
    "fuentes oficiales",
    "comunicado oficial",

    # Señales de potencial social / visual
    "viral",
    "se hace viral",
    "ha generado polémica",
    "indignación",
    "debate en redes",
    "reacciones",
    "captado en vídeo",
    "cámaras de seguridad",

    # Audiencia joven / formatos
    "jóvenes",
    "generación z",
    "redes sociales",
    "creadores de contenido",
    "streaming",
    "podcast",
]

KEYWORDS = sorted(
    set(
        kw
        for words in CATEGORIES.values()
        for kw in words
    )
    | set(EXTRA_KEYWORDS)
)


# ─────────────────────────────────────────────
# 3. EXCLUSIONES Y ALERTAS
# ─────────────────────────────────────────────

# Ruido poco útil para AC2ALITY.
#
# Importante:
# - Sí excluir loterías, cupones, horóscopos, parrilla TV y contenido puramente SEO/promocional.
# - No excluir marcas concretas: una marca puede ser noticia por consumo, multa, crisis,
#   campaña, producto defectuoso o fenómeno social.

EXCLUDE_TERMS = [
    # Azar / apuestas
    "horóscopo",
    "tarot",
    "zodiaco",
    "lotería",
    "bonoloto",
    "primitiva",
    "euromillones",
    "quiniela",
    "apuestas",
    "casino",
    "póker",
    "bono bienvenida",

    # Promociones / afiliación / retail puro
    "código descuento",
    "codigo descuento",
    "cupón descuento",
    "cupon descuento",
    "cupón",
    "cupon",
    "chollo",
    "oferta flash",
    "mejores ofertas",
    "precio mínimo",
    "amazon prime day",
    "black friday",
    "cyber monday",

    # TV SEO de bajo valor
    "programación tv",
    "programacion tv",
    "audiencias tv",
    "audiencia de ayer",
    "capítulo de hoy",
    "capitulo de hoy",
    "avance semanal",
    "horario y dónde ver",
    "dónde ver en tv",
    "donde ver en tv",
    "spoiler",

    # Contenido evergreen no noticioso
    "receta fácil",
    "receta facil",
    "cómo limpiar",
    "como limpiar",
    "trucos de limpieza",
]


# Palabras que no excluyen, pero marcan la noticia como sensible.
# Sirven para activar revisión humana reforzada, especialmente en sucesos,
# menores, salud, violencia, guerra y contenido viral potencialmente dañino.

SENSITIVE_TERMS = [
    # Violencia / delitos graves
    "asesinato",
    "homicidio",
    "feminicidio",
    "violación",
    "violacion",
    "agresión sexual",
    "agresion sexual",
    "abuso sexual",
    "maltrato",
    "violencia machista",
    "violencia de género",
    "violencia de genero",
    "violencia doméstica",
    "violencia domestica",
    "secuestro",
    "trata",
    "tráfico de personas",
    "trafico de personas",

    # Muerte / lesiones / desapariciones
    "suicidio",
    "autolesión",
    "autolesion",
    "muerte",
    "muere",
    "fallece",
    "fallecido",
    "cadáver",
    "cadaver",
    "desaparecido",
    "desaparecida",
    "accidente mortal",
    "heridos",
    "víctimas",
    "victimas",

    # Menores
    "menor",
    "menores",
    "niño",
    "nino",
    "niña",
    "nina",
    "bebé",
    "bebe",
    "adolescente",

    # Guerra / terrorismo / catástrofes
    "guerra",
    "atentado",
    "terrorismo",
    "bomba",
    "bombardeo",
    "tiroteo",
    "apuñalamiento",
    "arma blanca",
    "arma de fuego",
    "emergencia",
    "catástrofe",
    "catastrofe",
    "terremoto",
    "inundación",
    "inundacion",
    "incendio forestal",

    # Salud pública
    "brote",
    "epidemia",
    "pandemia",
    "virus mortal",
    "alerta sanitaria",
    "ingresado en urgencias",
    "sobredosis",

    # Riesgo reputacional / verificación
    "bulo",
    "fake news",
    "desinformación",
    "desinformacion",
    "vídeo manipulado",
    "video manipulado",
    "deepfake",
]


# Fuentes con mayor valor editorial.
#
# OJO:
# - Las claves deben coincidir exactamente con el nombre usado en FEEDS.
# - Pesos altos: agencias, servicio público, cabeceras de referencia y fuentes científicas.
# - Pesos medios: generalistas, TV informativa, internacional y tecnología.
# - Pesos bajos: entretenimiento, cultura pop y fuentes útiles como radar de tendencia.
#
# La idea no es censurar fuentes ligeras, sino que no dominen el ranking frente
# a una fuente primaria, agencia o cabecera de referencia.

SOURCE_WEIGHTS = {
    # ── Agencias / servicio público / máxima confianza ──────────────────────
    "EFE": 5,
    "EFE Verifica": 5,
    "Europa Press": 4,
    "Reuters World": 4,
    "AP News": 4,

    # ── Prensa generalista española de referencia ───────────────────────────
    "El País Últimas": 4,
    "El País España": 4,
    "El País Sociedad": 4,
    "El País Internacional": 4,
    "El País Economía": 3,
    "El País Ciencia": 4,
    "El País Tecnología": 4,
    "El País Deportes": 3,
    "El País Televisión": 2,
    "El País Gente": 2,

    "El Mundo": 3,
    "ABC": 3,
    "La Vanguardia Portada": 3,
    "La Vanguardia Sociedad": 3,
    "La Vanguardia Sucesos": 3,
    "La Vanguardia Internacional": 3,
    "La Vanguardia Tecnología": 3,
    "La Vanguardia Gente": 2,
    "elDiario.es": 3,
    "El Español": 2,
    "La Razón": 2,
    "20 Minutos": 2,
    "20 Minutos España": 2,
    "20 Minutos Madrid": 2,
    "Telemadrid": 2,

    # ── OKDiario / radar editorial AC2ALITY ─────────────────────────────────
    # Feeds añadidos como radar de actualidad, sucesos, deporte, cultura pop
    # y tendencias. Peso moderado/bajo para que no dominen frente a agencias,
    # servicio público y cabeceras de referencia.
    "OKDiario Portada": 3,
    "OKDiario España": 3,
    "OKDiario Sociedad": 3,
    "OKDiario Sucesos": 3,
    "OKDiario Internacional": 3,
    "OKDiario Deportes": 3,
    "OKDiario Fútbol": 3,
    "OKDiario Ciencia": 3,
    "OKDiario Cool Actualidad": 2,
    "OKDiario Famosos": 2,
    "OKDiario Redes Sociales": 2,

    # ── Televisión / portales de actualidad ─────────────────────────────────
    "Antena 3 Últimas": 3,
    "Antena 3 España": 3,
    "Antena 3 Sociedad": 3,
    "Antena 3 Mundo": 3,
    "Antena 3 Deportes": 3,
    "Telecinco Noticias": 2,
    "Telecinco Sociedad": 2,
    "La Sexta Noticias": 2,

    # ── Internacional de referencia ─────────────────────────────────────────
    "BBC Mundo": 4,
    "France 24 Español": 3,
    "DW Español": 3,
    "Euronews Español": 3,
    "The Guardian World": 3,
    "Washington Post World": 3,
    "New York Times World": 3,
    "CNN World": 2,

    # ── Deportes ─────────────────────────────────────────────────────────────
    "Marca": 2,
    "AS Portada": 2,
    "Mundo Deportivo": 2,
    "Sport": 1,
    "Antena 3 Deportes": 3,

    # ── Tecnología / ciencia / salud ────────────────────────────────────────
    "Xataka": 3,
    "Xataka Ciencia": 3,
    "Genbeta": 2,
    "Hipertextual": 2,
    "The Verge": 3,
    "TechCrunch": 2,
    "MIT Technology Review": 4,
    "Wired": 3,

    # ── Entretenimiento y cultura pop ───────────────────────────────────────
    # Útiles como radar, pero con menor peso para que no dominen el ranking.
    "Vertele": 2,
    "FórmulaTV": 1,
    "Diez Minutos": 1,
}

# Peso por defecto para fuentes no ponderadas.
# Se mantiene en 0 para que cualquier nuevo feed sin peso no reciba
# confianza editorial implícita. La validación de configuración lo avisará.
DEFAULT_SOURCE_WEIGHT = 0


def validate_configuration() -> list[str]:
    """
    Revisa incoherencias de configuración sin detener la ejecución.
    Sirve para detectar rápidamente cambios editoriales pendientes de revisar:
      - feeds duplicados por nombre;
      - feeds duplicados por URL;
      - feeds presentes en FEEDS sin peso en SOURCE_WEIGHTS.
    """
    warnings: list[str] = []

    feed_names = [name for name, _ in FEEDS]
    feed_urls = [url for _, url in FEEDS]

    duplicated_names = sorted(name for name, count in Counter(feed_names).items() if count > 1)
    duplicated_urls = sorted(url for url, count in Counter(feed_urls).items() if count > 1)
    feeds_without_weight = sorted(name for name in set(feed_names) if name not in SOURCE_WEIGHTS)

    if duplicated_names:
        warnings.append(
            "Feeds duplicados por nombre: " + ", ".join(duplicated_names)
        )

    if duplicated_urls:
        warnings.append(
            "Feeds duplicados por URL: " + ", ".join(duplicated_urls)
        )

    if feeds_without_weight:
        warnings.append(
            "Feeds sin peso en SOURCE_WEIGHTS: " + ", ".join(feeds_without_weight)
        )

    return warnings


# ─────────────────────────────────────────────
# 4. UTILIDADES DE TEXTO, FECHAS Y URLS
# ─────────────────────────────────────────────

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_local() -> datetime:
    return now_utc().astimezone(LOCAL_TZ)


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Extensiones que claramente no son imágenes de portada útiles (iconos, trackers de 1x1, etc.)
_IMAGE_URL_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
_BAD_IMAGE_HINTS = ("1x1", "pixel", "spacer", "blank.gif", "favicon", "tracker")


def _is_usable_image_url(url: str) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    lowered = url.lower()
    return not any(hint in lowered for hint in _BAD_IMAGE_HINTS)


def _best_from_media_list(items: Any) -> str:
    """media_content / media_thumbnail son listas de dicts con 'url' y a veces 'width'/'height'."""
    if not items:
        return ""

    candidates = []
    for item in items:
        url = ""
        if isinstance(item, dict):
            url = item.get("url", "")
        if url and _is_usable_image_url(url):
            try:
                width = int(item.get("width", 0) or 0)
            except (TypeError, ValueError):
                width = 0
            candidates.append((width, url))

    if not candidates:
        return ""

    # Preferimos la imagen más ancha disponible (suele ser la de mejor calidad).
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def extract_image_url(entry: Any, raw_summary_html: str = "") -> str:
    """
    Intenta extraer una imagen de portada del entry de feedparser, probando
    en orden las fuentes más fiables primero:
      1. media:content (MRSS) — El País, BBC, etc.
      2. media:thumbnail
      3. enclosures con type image/*
      4. links con rel="enclosure" y type image/*
      5. primer <img> dentro del HTML crudo del summary/content (Google News, blogs)
    Devuelve "" si no encuentra ninguna imagen utilizable.
    """
    try:
        media_content_url = _best_from_media_list(getattr(entry, "media_content", None) or entry.get("media_content"))
        if media_content_url:
            return media_content_url
    except Exception:
        pass

    try:
        media_thumb_url = _best_from_media_list(entry.get("media_thumbnail"))
        if media_thumb_url:
            return media_thumb_url
    except Exception:
        pass

    try:
        for enclosure in entry.get("enclosures", []) or []:
            url = enclosure.get("href") or enclosure.get("url", "")
            enclosure_type = (enclosure.get("type") or "").lower()
            if url and enclosure_type.startswith("image/") and _is_usable_image_url(url):
                return url
    except Exception:
        pass

    try:
        for link in entry.get("links", []) or []:
            link_type = (link.get("type") or "").lower()
            if link.get("rel") == "enclosure" and link_type.startswith("image/"):
                url = link.get("href", "")
                if url and _is_usable_image_url(url):
                    return url
    except Exception:
        pass

    # Último recurso: buscar un <img src="..."> en el HTML crudo del resumen/contenido.
    html_blobs = [raw_summary_html]
    try:
        for content_item in entry.get("content", []) or []:
            html_blobs.append(content_item.get("value", ""))
    except Exception:
        pass

    for blob in html_blobs:
        if not blob:
            continue
        match = _IMAGE_URL_RE.search(blob)
        if match and _is_usable_image_url(match.group(1)):
            return match.group(1)

    return ""


def normalize_text(text: str) -> str:
    """Minúsculas, sin tildes y con espacios normalizados."""
    text = strip_html(text)
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def short_url(url: str, max_len: int = 70) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        path = parsed.path.rstrip("/")
        value = f"{domain}{path}"
        return value[: max_len - 1] + "…" if len(value) > max_len else value
    except Exception:
        return url[: max_len - 1] + "…" if len(url) > max_len else url


def canonical_url(url: str) -> str:
    """Normaliza URL para deduplicar."""
    if not url:
        return ""

    try:
        parsed = urlparse(url.strip())
        scheme = "https"
        netloc = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.rstrip("/")

        # Eliminamos query/fragment para evitar duplicados por UTM.
        return urlunparse((scheme, netloc, path, "", "", ""))
    except Exception:
        return url.strip().lower()


def article_id(url: str, title: str) -> str:
    base = canonical_url(url) or normalize_text(title)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def parse_entry_datetime(entry: Any) -> datetime | None:
    """Devuelve fecha UTC si existe."""
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def format_datetime_utc(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def format_datetime_local(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.astimezone(LOCAL_TZ).strftime("%d/%m/%Y %H:%M")


def is_recent(entry: Any) -> bool:
    dt = parse_entry_datetime(entry)

    if not dt:
        return INCLUDE_UNDATED_ARTICLES

    return now_utc() - dt <= timedelta(hours=WINDOW_HOURS)


# ─────────────────────────────────────────────
# 5. FILTRADO, CLASIFICACIÓN Y SCORING
# ─────────────────────────────────────────────

# Prioridad editorial en caso de empate entre categorías.
# Cuanto más alto, más prioridad si dos categorías tienen el mismo número de hits.
CATEGORY_PRIORITY = {
    "SUCESOS": 11,
    "SOCIEDAD": 10,
    "MUNDO": 9,
    "POLÍTICA / LEYES": 8,
    "CIENCIA Y SALUD": 7,
    "TECNOLOGÍA E IA": 7,
    "CONSUMO / ECONOMÍA": 6,
    "DEPORTES": 6,
    "EDUCACIÓN": 5,
    "MEDIO AMBIENTE / CLIMA": 5,
    "CULTURA POP": 4,
    "OTRAS": 0,
}

# Bonus editorial por categoría.
# No significa que sean "mejores", sino que suelen ser más útiles para el radar AC2ALITY.
CATEGORY_SCORE_BONUS = {
    "SUCESOS": 2,
    "SOCIEDAD": 3,
    "MUNDO": 3,
    "POLÍTICA / LEYES": 2,
    "CIENCIA Y SALUD": 3,
    "TECNOLOGÍA E IA": 3,
    "CONSUMO / ECONOMÍA": 2,
    "DEPORTES": 2,
    "EDUCACIÓN": 2,
    "MEDIO AMBIENTE / CLIMA": 2,
    "CULTURA POP": 1,
}


def term_matches(text_norm: str, term: str) -> bool:
    """
    Matching más limpio que un simple 'term in text'.
    - Para términos de 1-2 caracteres, exige palabra completa.
      Ej: 'ia' no debe saltar dentro de 'noticia', 'familia' o 'hacia'.
    - Para términos largos o compuestos, permite coincidencia por frase normalizada.
    """
    term_norm = normalize_text(term)

    if not term_norm:
        return False

    # Keywords muy cortas: solo palabra completa.
    if len(term_norm) <= 2:
        pattern = rf"(?<![a-z0-9]){re.escape(term_norm)}(?![a-z0-9])"
        return re.search(pattern, text_norm) is not None

    # Términos compuestos o palabras largas.
    return term_norm in text_norm


def find_matches(text_norm: str, terms: list[str]) -> list[str]:
    matches = []

    for term in terms:
        if term_matches(text_norm, term):
            matches.append(term)

    return sorted(set(matches), key=lambda x: normalize_text(x))


def has_excluded_term(text_norm: str) -> bool:
    return any(term_matches(text_norm, term) for term in EXCLUDE_TERMS)


def sensitive_matches(text_norm: str) -> list[str]:
    return find_matches(text_norm, SENSITIVE_TERMS)


def classify_article(title: str, summary: str) -> tuple[str, int, list[str]]:
    """
    Clasifica por categoría.
    Devuelve:
      - categoría ganadora
      - número de coincidencias en esa categoría
      - keywords de esa categoría

    Si hay empate, usa CATEGORY_PRIORITY para evitar que gane una categoría
    solo por aparecer antes en el diccionario.
    """
    text_norm = normalize_text(f"{title} {summary}")

    best_category = "OTRAS"
    best_hits: list[str] = []
    best_priority = CATEGORY_PRIORITY.get("OTRAS", 0)

    for category, terms in CATEGORIES.items():
        hits = find_matches(text_norm, terms)
        priority = CATEGORY_PRIORITY.get(category, 0)

        if (
            len(hits) > len(best_hits)
            or (len(hits) == len(best_hits) and priority > best_priority)
        ):
            best_category = category
            best_hits = hits
            best_priority = priority

    return best_category, len(best_hits), best_hits


def editorial_risk_level(
    *,
    category: str,
    sensitive: list[str],
    title: str,
    summary: str,
) -> str:
    """
    Nivel de riesgo editorial.
    No bloquea la noticia: ayuda a saber qué requiere revisión humana.
    """
    text_norm = normalize_text(f"{title} {summary}")
    sensitive_norm = {normalize_text(term) for term in sensitive}

    high_risk_terms = {
        "violacion",
        "agresion sexual",
        "abuso sexual",
        "menor",
        "menores",
        "nino",
        "nina",
        "bebe",
        "suicidio",
        "autolesion",
        "asesinato",
        "homicidio",
        "feminicidio",
        "trata",
        "trafico de personas",
        "guerra",
        "atentado",
        "tiroteo",
        "bombardeo",
        "deepfake",
        "video manipulado",
        "bulo",
        "fake news",
    }

    if sensitive_norm & high_risk_terms:
        return "alto"

    if category in {"SUCESOS", "CIENCIA Y SALUD", "POLÍTICA / LEYES", "MUNDO"} and sensitive:
        return "alto"

    if sensitive:
        return "medio"

    if category in {"SUCESOS", "POLÍTICA / LEYES", "CIENCIA Y SALUD", "MUNDO"}:
        return "medio"

    if any(term_matches(text_norm, term) for term in [
        "polémica", "polemica", "acusado", "acusada", "denuncia",
        "investigan", "multa", "sanción", "sancion"
    ]):
        return "medio"

    return "bajo"


def recommended_format(category: str, score: int, is_sensitive: bool, risk: str) -> str:
    """
    Formato recomendado para trabajar la noticia.
    Esto no publica nada automáticamente: solo orienta la curación.
    """
    if risk == "alto":
        return "Revisión humana"

    if is_sensitive:
        return "5 cosas de hoy / revisión"

    if category in {"TECNOLOGÍA E IA", "CIENCIA Y SALUD", "CONSUMO / ECONOMÍA", "POLÍTICA / LEYES"}:
        return "Carrusel explicativo"

    if category in {"CULTURA POP", "DEPORTES"}:
        return "Reel"

    if category in {"MUNDO", "SOCIEDAD", "MEDIO AMBIENTE / CLIMA"} and score >= 14:
        return "Post individual"

    if score >= 16:
        return "Post individual"

    return "5 cosas de hoy"


def calculate_score(
    *,
    source_name: str,
    title: str,
    summary: str,
    category_hits: int,
    category: str,
    published_dt: datetime | None,
) -> int:
    """
    Score simple y explicable.
    No pretende sustituir criterio editorial: solo ordenar mejor.
    """
    text_norm = normalize_text(f"{title} {summary}")
    title_norm = normalize_text(title)

    score = 0

    # Coincidencias de categoría.
    score += category_hits * 3

    # Coincidencias generales.
    all_keyword_hits = find_matches(text_norm, KEYWORDS)
    score += min(len(all_keyword_hits), 8)

    # Si la keyword aparece en titular, pesa más.
    title_hits = find_matches(title_norm, KEYWORDS)
    score += min(len(title_hits) * 2, 8)

    # Fuentes más fiables o más útiles.
    score += SOURCE_WEIGHTS.get(source_name, DEFAULT_SOURCE_WEIGHT)

    # Recencia.
    if published_dt:
        age_hours = (now_utc() - published_dt).total_seconds() / 3600
        if age_hours <= 6:
            score += 4
        elif age_hours <= 12:
            score += 3
        elif age_hours <= 24:
            score += 2
        elif age_hours <= 48:
            score += 1

    # Bonus por categorías útiles para el desk AC2ALITY.
    score += CATEGORY_SCORE_BONUS.get(category, 0)

    # Señales de formato / actualidad muy útiles para AC2ALITY.
    if any(term_matches(text_norm, term) for term in [
        "lo que se sabe",
        "que ha pasado",
        "qué ha pasado",
        "claves",
        "ultima hora",
        "última hora",
        "en directo",
        "viral",
        "se hace viral",
        "imagenes",
        "imágenes",
        "video",
        "vídeo",
    ]):
        score += 2

    # Penalización suave para evitar que sucesos sensibles dominen todo el ranking.
    # No se elimina la noticia: solo baja un poco frente a piezas menos delicadas.
    sensitive = sensitive_matches(text_norm)
    if sensitive and category == "SUCESOS":
        score -= 1

    return score


def build_article(source_name: str, entry: Any) -> dict[str, Any] | None:
    title = strip_html(entry.get("title", "")).strip()
    url = entry.get("link", "").strip()
    raw_summary_html = entry.get("summary", "") or entry.get("description", "")
    summary = strip_html(raw_summary_html)

    if not title or not url:
        return None

    text_norm = normalize_text(f"{title} {summary}")

    if has_excluded_term(text_norm):
        return None

    category, category_hit_count, category_keywords = classify_article(title, summary)
    all_matches = find_matches(text_norm, KEYWORDS)
    sensitive = sensitive_matches(text_norm)

    # Si no hay ninguna coincidencia editorial, no entra.
    if not all_matches:
        return None

    published_dt = parse_entry_datetime(entry)

    score = calculate_score(
        source_name=source_name,
        title=title,
        summary=summary,
        category_hits=category_hit_count,
        category=category,
        published_dt=published_dt,
    )

    if score < MIN_SCORE:
        return None

    risk = editorial_risk_level(
        category=category,
        sensitive=sensitive,
        title=title,
        summary=summary,
    )

    format_suggestion = recommended_format(
        category=category,
        score=score,
        is_sensitive=bool(sensitive),
        risk=risk,
    )

    image_url = extract_image_url(entry, raw_summary_html)

    return {
        "id": article_id(url, title),
        "title": title,
        "url": url,
        "url_short": short_url(url),
        "image": image_url,
        "source": source_name,
        "published": format_datetime_utc(published_dt),
        "published_local": format_datetime_local(published_dt),
        "published_iso": published_dt.isoformat() if published_dt else "",
        "category": category,
        "score": score,
        "matched_keywords": all_matches[:12],
        "category_keywords": category_keywords[:12],
        "is_sensitive": bool(sensitive),
        "sensitive_terms": sensitive[:10],
        "editorial_risk": risk,
        "needs_human_review": risk in {"medio", "alto"},
        "recommended_format": format_suggestion,
        "summary": summary[:500],
    }


def is_article_recent_or_allowed(entry: Any) -> bool:
    if is_recent(entry):
        return True
    return False


# ─────────────────────────────────────────────
# 6. FETCH RSS
# ─────────────────────────────────────────────

# Caracteres de control no válidos en XML 1.0 (causan "not well-formed (invalid token)").
_INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Etiquetas de cierre de raíz habituales en feeds RSS/Atom/RDF.
_ROOT_CLOSING_TAGS = ("</rss>", "</feed>", "</rdf:RDF>")


def _download_raw_bytes(url: str, timeout: int = FEED_TIMEOUT_SECONDS) -> bytes:
    """Descarga el feed como bytes crudos, sin pasar por el opener interno de feedparser."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=_SSL_CONTEXT) as response:
        return response.read()


def _build_ssl_context() -> ssl.SSLContext:
    """
    Usa los certificados de certifi si están disponibles. Es imprescindible en
    la app empaquetada de macOS, donde Python no encuentra los del sistema.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_SSL_CONTEXT = _build_ssl_context()


def _sanitize_xml_bytes(raw: bytes) -> str:
    """
    Decodifica los bytes de forma tolerante y elimina caracteres de control
    inválidos en XML. Esto evita el típico mismatch "declared as us-ascii,
    but parsed as utf-8" y muchos errores "not well-formed (invalid token)".
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    # Quita BOM si aparece a mitad de cadena tras decodificar mal.
    text = text.lstrip("\ufeff")
    return _INVALID_XML_CHARS.sub("", text)


def _truncate_after_root(text: str) -> str | None:
    """
    Corrige el error "junk after document element": recorta el documento
    justo después de la etiqueta de cierre de la raíz, descartando cualquier
    contenido sobrante (HTML de error, texto extra, etc.) que el servidor
    haya añadido a continuación.
    """
    for closing_tag in _ROOT_CLOSING_TAGS:
        idx = text.rfind(closing_tag)
        if idx != -1:
            return text[: idx + len(closing_tag)]
    return None


def _parse_with_recovery(name: str, raw: bytes) -> tuple[Any, str | None]:
    """
    Intenta parsear el feed en varias pasadas, de menos a más agresiva:
      1. Bytes originales (deja que feedparser detecte la codificación).
      2. Texto saneado (sin caracteres de control inválidos).
      3. Texto saneado y truncado tras la etiqueta raíz (corrige "junk after
         document element").
    Devuelve el primer resultado con entries, o el último intento si ninguno
    tuvo éxito.
    """
    feed = feedparser.parse(raw)
    if feed.entries:
        return feed, (f"Feed con incidencias de parseo: {feed.bozo_exception}" if feed.bozo else None)

    sanitized = _sanitize_xml_bytes(raw)
    feed = feedparser.parse(sanitized)
    if feed.entries:
        return feed, f"Feed saneado (caracteres de control inválidos) — revisar fuente: {name}"

    truncated = _truncate_after_root(sanitized)
    if truncated is not None:
        feed = feedparser.parse(truncated)
        if feed.entries:
            return feed, f"Feed truncado tras la raíz (contenido sobrante del servidor) — revisar fuente: {name}"

    # Ningún intento recuperó entradas: devolvemos el último resultado tal cual.
    error = f"Error al parsear el feed: {feed.bozo_exception}" if feed.bozo else None
    return feed, error


def fetch_feed(name: str, url: str) -> tuple[list[dict[str, Any]], str | None]:
    """
    Descarga y parsea un feed RSS.
    Devuelve:
      (artículos, error)
    """
    try:
        try:
            raw = _download_raw_bytes(url)
        except (URLError, socket.timeout, OSError) as exc:
            # Si la descarga manual falla (DNS, timeout, TLS...), recurrimos
            # al mecanismo interno de feedparser como último recurso.
            feed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT})
            if not feed.entries:
                return [], f"Error de descarga: {exc}"
            raw = None

        if raw is not None:
            feed, parse_error = _parse_with_recovery(name, raw)
        else:
            parse_error = f"Feed con incidencias de parseo: {feed.bozo_exception}" if feed.bozo else None

        if feed.bozo and not feed.entries:
            return [], parse_error or f"Error al parsear el feed: {feed.bozo_exception}"

        articles = []

        for entry in feed.entries[:MAX_ARTICLES_PER_SOURCE * 3]:
            if not is_article_recent_or_allowed(entry):
                continue

            article = build_article(name, entry)

            if article:
                articles.append(article)

            if len(articles) >= MAX_ARTICLES_PER_SOURCE:
                break

        return articles, parse_error

    except Exception as exc:
        return [], str(exc)


# ─────────────────────────────────────────────
# 7. DEDUPLICACIÓN Y AGRUPACIÓN
# ─────────────────────────────────────────────

def title_key(title: str) -> str:
    value = normalize_text(title)
    value = re.sub(r"[^a-z0-9 ]+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:120]


def dedupe_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Deduplicación simple:
      1. URL canónica.
      2. Título normalizado.
    Si hay duplicado, conserva el de mayor score.
    """
    best_by_key: dict[str, dict[str, Any]] = {}

    for article in articles:
        url_key = canonical_url(article.get("url", ""))
        t_key = title_key(article.get("title", ""))
        key = url_key or t_key

        if not key:
            continue

        existing = best_by_key.get(key)

        if not existing or article.get("score", 0) > existing.get("score", 0):
            best_by_key[key] = article

    # Segunda pasada por título, para duplicados con URLs diferentes.
    best_by_title: dict[str, dict[str, Any]] = {}

    for article in best_by_key.values():
        key = title_key(article.get("title", ""))

        if not key:
            continue

        existing = best_by_title.get(key)

        if not existing or article.get("score", 0) > existing.get("score", 0):
            best_by_title[key] = article

    deduped = list(best_by_title.values())

    deduped.sort(
        key=lambda a: (
            a.get("score", 0),
            a.get("published_iso", ""),
        ),
        reverse=True,
    )

    return deduped[:MAX_TOTAL_ARTICLES]


def group_articles_by_source(
    source_results: list[dict[str, Any]],
    kept_articles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    kept_ids = {a["id"] for a in kept_articles}

    output_sources = []

    for source in source_results:
        filtered_articles = [
            article
            for article in source["articles"]
            if article["id"] in kept_ids
        ]

        output_sources.append({
            "name": source["name"],
            "url": source["url"],
            "articles": filtered_articles,
            "count": len(filtered_articles),
            "error": source["error"],
        })

    return output_sources


def build_category_summary(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}

    for article in articles:
        category = article.get("category") or "OTRAS"
        counts[category] = counts.get(category, 0) + 1

    return [
        {"name": category, "count": count}
        for category, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    ]


def build_source_summary(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": source["name"],
            "count": source["count"],
            "error": source["error"],
        }
        for source in sorted(sources, key=lambda item: item["count"], reverse=True)
    ]


# ─────────────────────────────────────────────
# 8. EJECUCIÓN (CLI y app de escritorio)
# ─────────────────────────────────────────────
# run_digest() es la función que usa la app de escritorio: descarga las
# fuentes en paralelo e informa del progreso mediante un callback, sin
# imprimir nada. main() la envuelve para seguir funcionando en terminal y
# en GitHub Actions exactamente igual que antes.

MAX_PARALLEL_FEEDS = 12

ProgressCallback = Callable[[dict[str, Any]], None]


def build_digest_output(
    source_results: list[dict[str, Any]],
    all_articles: list[dict[str, Any]],
) -> dict[str, Any]:
    deduped_articles = dedupe_articles(all_articles)
    output_sources = group_articles_by_source(source_results, deduped_articles)

    generated_utc = now_utc()
    generated_local = generated_utc.astimezone(LOCAL_TZ)

    return {
        "project": PROJECT_NAME,
        "generated_at": generated_utc.isoformat(),
        "generated_at_local": generated_local.isoformat(),
        "date": generated_local.strftime("%d/%m/%Y"),
        "timezone": "Europe/Madrid",
        "window_hours": WINDOW_HOURS,
        "total_feeds": len(FEEDS),
        "total_articles_raw": len(all_articles),
        "total_articles": len(deduped_articles),
        "sources_with_errors": sum(1 for source in output_sources if source["error"]),
        "categories": build_category_summary(deduped_articles),
        "source_summary": build_source_summary(output_sources),
        "articles": deduped_articles,
        "sources": output_sources,
    }


def write_json_atomic(path: str | os.PathLike[str], data: dict[str, Any]) -> None:
    """Escribe en un temporal y lo renombra: nunca deja un digest.json a medias."""
    path = os.fspath(path)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".digest-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def run_digest(
    output_path: str | os.PathLike[str] | None = OUTPUT_FILE,
    progress: ProgressCallback | None = None,
    max_workers: int = MAX_PARALLEL_FEEDS,
) -> dict[str, Any]:
    """
    Descarga todas las fuentes en paralelo, genera el digest y (opcionalmente)
    lo guarda en output_path.

    progress recibe eventos dict con "type":
      start        {total}
      feed_start   {index, name}
      feed_done    {index, name, count, error, done, total, articles_so_far}
      processing   {}
      done         {total_articles, sources_with_errors, output_path}
    """
    def emit(event: dict[str, Any]) -> None:
        if progress:
            try:
                progress(event)
            except Exception:
                pass  # un fallo de la interfaz nunca debe parar la descarga

    total = len(FEEDS)
    emit({"type": "start", "total": total})

    results: list[dict[str, Any] | None] = [None] * total
    done = 0
    articles_so_far = 0
    lock = threading.Lock()

    def worker(index: int, name: str, url: str) -> None:
        nonlocal done, articles_so_far
        emit({"type": "feed_start", "index": index, "name": name})
        articles, error = fetch_feed(name, url)
        results[index] = {"name": name, "url": url, "articles": articles, "error": error}
        with lock:
            done += 1
            articles_so_far += len(articles)
            snapshot = {"done": done, "articles_so_far": articles_so_far}
        emit({
            "type": "feed_done",
            "index": index,
            "name": name,
            "count": len(articles),
            "error": error,
            "total": total,
            **snapshot,
        })

    workers = max(1, min(max_workers, total))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="feed") as pool:
        futures = [pool.submit(worker, i, name, url) for i, (name, url) in enumerate(FEEDS)]
        for future in as_completed(futures):
            future.result()

    emit({"type": "processing"})

    # Se conserva el orden original de FEEDS para que el resultado sea estable.
    source_results = [r for r in results if r is not None]
    all_articles = [a for r in source_results for a in r["articles"]]
    output = build_digest_output(source_results, all_articles)

    if output_path:
        write_json_atomic(output_path, output)

    emit({
        "type": "done",
        "total_articles": output["total_articles"],
        "sources_with_errors": output["sources_with_errors"],
        "output_path": os.fspath(output_path) if output_path else None,
    })
    return output


def main() -> int:
    start = now_utc()

    print(
        f"[{start.strftime('%Y-%m-%d %H:%M UTC')}] "
        f"Iniciando fetch Ac2ality de {len(FEEDS)} feeds..."
    )

    config_warnings = validate_configuration()
    if config_warnings:
        print("\nAVISOS DE CONFIGURACIÓN:")
        for warning in config_warnings:
            print(f"  ⚠️ {warning}")
        print()

    def cli_progress(event: dict[str, Any]) -> None:
        if event["type"] == "feed_done":
            print(
                f"  [{event['done']:>3}/{event['total']}] {event['name']}: "
                f"{event['count']} artículos"
                + (f" | AVISO: {event['error']}" if event["error"] else ""),
                flush=True,
            )

    output = run_digest(OUTPUT_FILE, progress=cli_progress)

    print()
    print(f"Total artículos brutos: {output['total_articles_raw']}")
    print(f"Total artículos tras deduplicar: {output['total_articles']}")
    print(f"Fuentes con error/aviso: {output['sources_with_errors']}")
    print(f"Fichero guardado: {OUTPUT_FILE}")
    print(f"Tiempo total: {(now_utc() - start).total_seconds():.1f} s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
