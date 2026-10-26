# app/utils/helpers.py
import os
from flask import current_app
from werkzeug.utils import secure_filename

import uuid
from flask import current_app

EXTENSIONES_IMAGEN = {'png', 'jpg', 'jpeg', 'webp'}
EXTENSIONES_DOCUMENTO = {'pdf', 'jpg', 'jpeg', 'png'}

def extension_permitida(nombre_archivo, extensiones):
    return '.' in nombre_archivo and \
           nombre_archivo.rsplit('.', 1)[1].lower() in extensiones


def guardar_archivo(archivo, subcarpeta):
    """Guarda un archivo subido en instance/uploads/<subcarpeta> con nombre aleatorio; retorna su ruta relativa."""
    if not archivo or archivo.filename == '':
        return None

    extensiones = EXTENSIONES_IMAGEN if subcarpeta in ('fotos', 'ofertas') else EXTENSIONES_DOCUMENTO
    if not extension_permitida(archivo.filename, extensiones):
        return None

    nombre = f"{uuid.uuid4().hex}.{archivo.filename.rsplit('.', 1)[1].lower()}"
    carpeta = os.path.join(current_app.instance_path, 'uploads', subcarpeta)
    os.makedirs(carpeta, exist_ok=True)
    archivo.save(os.path.join(carpeta, nombre))
    return f'uploads/{subcarpeta}/{nombre}'


def borrar_archivo(ruta):
    """Borra un archivo guardado con guardar_archivo. Ignora enlaces web y rutas fuera de instance/uploads."""
    if not ruta or not ruta.startswith('uploads/'):
        return
    base = os.path.join(current_app.instance_path, 'uploads')
    archivo = os.path.normpath(os.path.join(current_app.instance_path, ruta))
    if archivo.startswith(base + os.sep) and os.path.isfile(archivo):
        os.remove(archivo)


def alcance_personal(personal):
    """(id_facultad, id_programa) a los que está limitado el personal; (None, None) = global."""
    ambito = personal.rol.ambito
    if ambito == 'facultad':
        return personal.id_facultad or 0, None
    if ambito == 'programa':
        return None, personal.id_programa or 0
    return None, None