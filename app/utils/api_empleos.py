# app/utils/api_empleos.py
import os
import re
import json
import hashlib
from datetime import datetime, timedelta

from dotenv import load_dotenv
from serpapi import GoogleSearch

from app.extensions import db
from app.models import OfertaLaboral

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# ============================================================
# PRESUPUESTO DE CONSULTAS
# ============================================================
LIMITE_PLAN = 200                       # consultas por mes del plan
MARGEN = 20                             # colchón por si algo falla
MAX_MENSUAL = LIMITE_PLAN - MARGEN      # tope real: 180
VIGENCIA_DIAS = 21                      # cuánto dura una oferta tras verla (semanal + colchón)
MAX_OFERTAS = 600                      # Un limite de oferta en la db

# Contador local (archivo en la carpeta instance/)
ARCHIVO_USO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "instance", "uso_serpapi.json")
)

# ============================================================
# QUÉ SE BUSCA (ordenado por prioridad: si falta cupo, se recortan las últimas)
# "pais" es el nombre que se guardará en la ubicación y que usará el filtro.
# ============================================================
PLAN_BUSQUEDAS = [
    # --- Perú ---
    {"q": "soporte TI redes",           "location": "Lima, Peru", "gl": "pe", "pais": "Perú"},
    {"q": "ingeniero de sistemas",      "location": "Peru",       "gl": "pe", "pais": "Perú"},
    {"q": "analista de sistemas",       "location": "Peru",       "gl": "pe", "pais": "Perú"},
    {"q": "desarrollador de software",  "location": "Peru",       "gl": "pe", "pais": "Perú"},
    # --- España ---
    {"q": "ingeniero de software",      "location": "Spain",        "gl": "es", "pais": "España"},
    {"q": "desarrollador de software",  "location": "Madrid, Spain", "gl": "es", "pais": "España"},
    {"q": "administrador de sistemas redes", "location": "Spain",   "gl": "es", "pais": "España"},
    # --- Estados Unidos ---
    {"q": "software engineer",          "location": "United States", "gl": "us", "pais": "Estados Unidos"},
    {"q": "software developer remote",  "location": "United States", "gl": "us", "pais": "Estados Unidos"},
    {"q": "network engineer",           "location": "United States", "gl": "us", "pais": "Estados Unidos"},
    # Para ampliar más adelante (cada línea nueva = 1 consulta por semana):
    {"q": "ingeniero de software", "location": "Mexico",   "gl": "mx", "pais": "México"},
    {"q": "ingeniero de software", "location": "Chile",    "gl": "cl", "pais": "Chile"},
    {"q": "ingeniero de software", "location": "Colombia", "gl": "co", "pais": "Colombia"},
]

# ============================================================
# FILTRO DE RELEVANCIA (solo se guarda si el título tiene alguna de estas palabras)
# ============================================================
PALABRAS_CLAVE = [
    "sistemas", "systems", "software", "desarrollador", "desarrolladora", "developer",
    "programador", "programadora", "programmer", "devops", "backend", "back-end",
    "frontend", "front-end", "full stack", "fullstack", "datos", "data", "redes",
    "network", "cloud", "ciberseguridad", "cybersecurity", "infraestructura",
    "infrastructure", "sysadmin", "sre", "qa", "ti", "it", "soporte ti", "it support",
    "help desk", "mesa de ayuda",
]
PATRON_RELEVANTE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in PALABRAS_CLAVE) + r")\b", re.IGNORECASE
)


# ============================================================
# CONTADOR DE CONSULTAS
# ============================================================
def _leer_uso():
    mes = datetime.now().strftime("%Y-%m")
    try:
        with open(ARCHIVO_USO, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (FileNotFoundError, ValueError):
        datos = {}
    if datos.get("mes") != mes:          # mes nuevo: se reinicia el contador
        datos = {"mes": mes, "usadas": 0}
    return datos


def _guardar_uso(datos):
    os.makedirs(os.path.dirname(ARCHIVO_USO), exist_ok=True)
    with open(ARCHIVO_USO, "w", encoding="utf-8") as f:
        json.dump(datos, f)


def estado_presupuesto():
    """Para mostrar en el panel o probar en la consola."""
    uso = _leer_uso()
    return {"mes": uso["mes"], "usadas": uso["usadas"], "tope": MAX_MENSUAL,
            "restantes": MAX_MENSUAL - uso["usadas"]}


# ============================================================
# AYUDAS
# ============================================================
def _normalizar_ubicacion(ubicacion_raw, pais):
    """Devuelve siempre 'Ciudad, País' para que el filtro por país funcione."""
    texto = (ubicacion_raw or "").strip()
    if not texto or texto.lower() in ("anywhere", "cualquier lugar", "remoto"):
        return f"Remoto, {pais}"[:200]
    ciudad = texto.split(",")[0].strip()
    if ciudad.lower() == pais.lower():
        return pais
    return f"{ciudad}, {pais}"[:200]


def _limpiar_url(raw_url):
    if not raw_url:
        return None
    # Quita parámetros de rastreo (?utm_...) que causan bloqueos 403
    return raw_url.split('?utm_')[0].split('&utm_')[0]

def _depurar_ofertas(hoy, maximo=MAX_OFERTAS):
    """Se ejecuta al terminar cada sincronización. Nunca toca las ofertas manuales.
    1) Borra las automáticas vencidas (las que dejaron de aparecer en la búsqueda).
    2) Si aun así hay más de `maximo` ofertas, borra las automáticas más antiguas."""
    borradas = OfertaLaboral.query.filter(
        OfertaLaboral.fuente == 'automatico', OfertaLaboral.fecha_vencimiento < hoy
    ).delete(synchronize_session=False)

    exceso = OfertaLaboral.query.count() - maximo
    if exceso > 0:
        ids = [i for (i,) in db.session.query(OfertaLaboral.id_oferta)
               .filter(OfertaLaboral.fuente == 'automatico')
               .order_by(OfertaLaboral.fecha_publicacion.asc(), OfertaLaboral.id_oferta.asc())
               .limit(exceso).all()]
        if ids:
            borradas += OfertaLaboral.query.filter(
                OfertaLaboral.id_oferta.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return borradas

# ============================================================
# SINCRONIZACIÓN
# ============================================================
def sincronizar_empleos_externos(plan=None, max_busquedas=36):
    """
    Recorre el plan de búsquedas en SerpApi (Google Jobs) y guarda ofertas
    de sistemas/software/redes de Perú y el extranjero.
    Gasta como máximo `max_busquedas` consultas por ejecución y nunca pasa
    del tope mensual (MAX_MENSUAL).
    """
    if not SERPAPI_KEY:
        print("!!!! Error: SERPAPI_KEY no configurada en el archivo .env")
        return {"status": "error", "message": "Falta API Key"}

    plan = plan or PLAN_BUSQUEDAS
    uso = _leer_uso()
    disponibles = MAX_MENSUAL - uso["usadas"]
    if disponibles <= 0:
        print(f"!!!! Presupuesto mensual agotado ({uso['usadas']}/{MAX_MENSUAL}).")
        return {"status": "error", "message": "Presupuesto mensual agotado"}

    cupo = min(max_busquedas, disponibles)
    hoy = datetime.now().date()
    resumen = {"status": "success", "busquedas": 0, "nuevos": 0, "renovados": 0,
               "descartados": 0, "por_pais": {}}
    vistos = set()   # evita repetir ofertas que salen en varias búsquedas

    for busqueda in plan[:cupo]:
        params = {
            "engine": "google_jobs",
            "q": busqueda["q"],
            "location": busqueda["location"],
            "gl": busqueda["gl"],
            "hl": "es",          # español para que los nombres de lugar sean consistentes
            "api_key": SERPAPI_KEY,
        }

        # Se cuenta ANTES de consultar: si falla a medias, mejor pasarse por seguridad
        uso["usadas"] += 1
        _guardar_uso(uso)
        resumen["busquedas"] += 1

        try:
            resultados = GoogleSearch(params).get_dict()
        except Exception as e:
            print(f"!!!! Error de red en '{busqueda['q']}' / {busqueda['location']}: {e}")
            continue

        error = resultados.get("error")
        if error:
            if "run out" in error.lower():
                print(f"!!!! SerpApi sin consultas disponibles: {error}")
                resumen["status"] = "error"
                resumen["message"] = error
                break
            if "hasn't returned any results" not in error:
                print(f"!!!! Error de SerpApi: {error}")
            continue

        nuevos_aqui = 0
        try:
            for job in resultados.get("jobs_results", []):
                titulo = (job.get("title") or "").strip()
                job_id_raw = job.get("job_id")
                if not job_id_raw or not titulo:
                    continue

                if not PATRON_RELEVANTE.search(titulo):
                    resumen["descartados"] += 1
                    continue

                job_id_externo = hashlib.sha256(job_id_raw.encode("utf-8")).hexdigest()
                if job_id_externo in vistos:
                    continue
                vistos.add(job_id_externo)

                existente = OfertaLaboral.query.filter_by(id_externo_job=job_id_externo).first()
                if existente:
                    # Sigue publicada en Google: se alarga su vigencia (si no fue desactivada)
                    if existente.activa:
                        existente.fecha_vencimiento = hoy + timedelta(days=VIGENCIA_DIAS)
                        resumen["renovados"] += 1
                    continue

                apply_options = job.get("apply_options") or []
                raw_url = apply_options[0].get("link") if apply_options else None
                detected = job.get("detected_extensions") or {}
                salario = detected.get("salary")

                nueva = OfertaLaboral(
                    id_creado_por=None,
                    empresa_nombre=(job.get("company_name") or "Confidencial")[:200],
                    id_sector=None,
                    titulo=titulo[:255],
                    descripcion=job.get("description", ""),
                    modalidad="Remoto" if detected.get("work_from_home") else None,
                    jornada=(detected.get("schedule_type") or None) and detected["schedule_type"][:80],
                    remuneracion=str(salario)[:80] if salario else None,
                    ubicacion=_normalizar_ubicacion(job.get("location"), busqueda["pais"]),
                    ruta_imagen=job.get("thumbnail"),
                    url_original=_limpiar_url(raw_url),
                    id_externo_job=job_id_externo,
                    fuente="automatico",
                    fecha_publicacion=hoy,
                    fecha_vencimiento=hoy + timedelta(days=VIGENCIA_DIAS),
                    activa=True,
                )
                db.session.add(nueva)
                nuevos_aqui += 1

            db.session.commit()   # se guarda tras cada búsqueda
        except Exception as e:
            db.session.rollback()
            print(f"!!!! Error al guardar ofertas de '{busqueda['q']}': {e}")
            continue

        resumen["nuevos"] += nuevos_aqui
        pais = busqueda["pais"]
        resumen["por_pais"][pais] = resumen["por_pais"].get(pais, 0) + nuevos_aqui
        print(f"🔎 {busqueda['q']} | {busqueda['location']}: {nuevos_aqui} nuevas")

    resumen['depuradas'] = _depurar_ofertas(hoy)
    print(f"!!!! Sincronización terminada: {resumen['nuevos']} nuevas, "
          f"{resumen['renovados']} renovadas, {resumen['descartados']} descartadas. "
          f"Uso del mes: {uso['usadas']}/{MAX_MENSUAL}")
    return resumen