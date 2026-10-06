# app/utils/api_empleos.py
import os
import hashlib
from datetime import datetime, timedelta
from dotenv import load_dotenv
from serpapi import GoogleSearch
from app.extensions import db
from app.models import OfertaLaboral  # Modelo actualizado

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")


def sincronizar_empleos_externos(busqueda="Sistemas Lima OR Pasco OR Remoto"):
    """
    Consulta SerpApi (Google Jobs) e inserta nuevas ofertas laborales
    en la BD local evitando duplicados mediante el hash del id_externo_job.
    """
    if not SERPAPI_KEY:
        print("!!!! Error: SERPAPI_KEY no configurada en el archivo .env")
        return {"status": "error", "message": "Falta API Key"}

    params = {
        "engine": "google_jobs",
        "q": busqueda,
        "hl": "es",
        "gl": "pe",
        "api_key": SERPAPI_KEY
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()

        if "error" in results:
            print(f"!!!! Error de SerpApi: {results['error']}")
            return {"status": "error", "message": results["error"]}

        jobs = results.get("jobs_results", [])
        print(f"🔎 SerpApi devolvió {len(jobs)} ofertas encontradas para '{busqueda}'.")

        if not jobs:
            print("!!!! No se encontraron nuevos empleos con esa búsqueda.")
            return {"status": "success", "nuevos": 0}

        nuevas_inserciones = 0

        for job in jobs:
            job_id_raw = job.get("job_id")
            if not job_id_raw:
                continue

            # Generamos un Hash SHA-256 único de 64 caracteres para el job_id
            job_id_externo = hashlib.sha256(job_id_raw.encode('utf-8')).hexdigest()

            # Verificar si la oferta ya fue sincronizada anteriormente
            oferta_existente = OfertaLaboral.query.filter_by(id_externo_job=job_id_externo).first()
            if oferta_existente:
                continue

            # Extracción de campos del JSON
            titulo = job.get("title", "Empleo de Sistemas")
            empresa_nombre = job.get("company_name", "Confidencial")
            ubicacion_job = job.get("location", "Perú")
            descripcion = job.get("description", "")
            
            # --- LIMPIEZA DE LA URL DE POSTULACIÓN ---
            apply_options = job.get("apply_options", [])
            raw_url = apply_options[0].get("link") if apply_options else None

            if raw_url:
                # Elimina los parámetros de rastreo (?utm_...) que causan bloqueos 403
                url_original = raw_url.split('?utm_')[0].split('&utm_')[0]
            else:
                url_original = None

            # Metadatos adicionales
            detected = job.get("detected_extensions", {})
            remuneracion = str(detected.get("salary")) if detected.get("salary") else None
            jornada = detected.get("schedule_type")
            ruta_imagen = job.get("thumbnail")

            # Fechas (vigencia de 15 días)
            fecha_publicacion = datetime.now().date()
            fecha_vencimiento = fecha_publicacion + timedelta(days=15)

            # Creación del registro alineado con models.py
            nueva_oferta = OfertaLaboral(
                id_creado_por=None,
                empresa_nombre=empresa_nombre,
                id_sector=None,
                titulo=titulo,
                descripcion=descripcion,
                jornada=jornada,
                remuneracion=remuneracion,
                ubicacion=ubicacion_job,
                ruta_imagen=ruta_imagen,
                url_original=url_original,
                id_externo_job=job_id_externo,
                fuente='automatico',
                fecha_publicacion=fecha_publicacion,
                fecha_vencimiento=fecha_vencimiento,
                activa=True
            )

            db.session.add(nueva_oferta)
            nuevas_inserciones += 1

        db.session.commit()
        print(f"!!!! Sincronización exitosa: {nuevas_inserciones} ofertas registradas en la base de datos.")
        return {"status": "success", "nuevos": nuevas_inserciones}

    except Exception as e:
        db.session.rollback()
        print(f"!!!! Error al guardar ofertas en la BD: {e}")
        return {"status": "error", "message": str(e)}