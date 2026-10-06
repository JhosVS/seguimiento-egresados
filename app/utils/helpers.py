# app/utils/helpers.py
import os
from werkzeug.utils import secure_filename

EXTENSIONES_IMAGEN = {'png', 'jpg', 'jpeg', 'webp'}
EXTENSIONES_DOCUMENTO = {'pdf', 'jpg', 'jpeg', 'png'}

def extension_permitida(nombre_archivo, extensiones):
    return '.' in nombre_archivo and \
           nombre_archivo.rsplit('.', 1)[1].lower() in extensiones

def guardar_archivo(archivo, subcarpeta):
    """Guarda un archivo subido en static/uploads/<subcarpeta> y retorna su ruta relativa."""
    if not archivo or archivo.filename == '':
        return None

    extensiones = EXTENSIONES_IMAGEN if subcarpeta in ('fotos', 'ofertas') else EXTENSIONES_DOCUMENTO
    
    if not extension_permitida(archivo.filename, extensiones):
        return None

    nombre = secure_filename(archivo.filename)
    carpeta = os.path.join('app', 'static', 'uploads', subcarpeta)
    os.makedirs(carpeta, exist_ok=True)
    
    ruta_disco = os.path.join(carpeta, nombre)
    archivo.save(ruta_disco)
    
    return f"uploads/{subcarpeta}/{nombre}"

def alcance_personal(personal):
    """(id_facultad, id_programa) a los que está limitado el personal; (None, None) = global."""
    ambito = personal.rol.ambito
    if ambito == 'facultad':
        return personal.id_facultad or 0, None   # 0 = no coincide con nada si faltara el dato
    if ambito == 'programa':
        return None, personal.id_programa or 0
    return None, None