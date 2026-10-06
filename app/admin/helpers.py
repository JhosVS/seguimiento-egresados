# app/admin/helpers.py
from functools import wraps
from flask import redirect, url_for, flash, request
from flask_login import current_user
from app.extensions import db
from app.models import Rol, Personal, ProgramaEstudio, Respuesta, Egresado, Curricula


def solo_admin(f):
    @wraps(f)
    def decorado(*args, **kwargs):
        if not current_user.is_authenticated or current_user.es_egresado():
            flash('No tienes permiso para acceder.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorado


def requiere_rol(*roles_permitidos):
    def decorador(f):
        @wraps(f)
        def decorado(*args, **kwargs):
            if not current_user.is_authenticated or current_user.es_egresado():
                flash('No tienes permiso para acceder.', 'danger')
                return redirect(url_for('auth.login'))
            if current_user.rol_activo_nombre() not in roles_permitidos:
                flash('No tienes permiso para acceder a esta sección.', 'danger')
                return redirect(url_for('admin.dashboard'))
            return f(*args, **kwargs)
        return decorado
    return decorador


def _facultades_de_coordinador(id_personal):
    p = Personal.query.get(id_personal)
    if not p or not p.id_facultad:
        return []
    return [p.id_facultad]


def _ids_personal_gestionado_por_coordinador(id_personal_coordinador):
    ids_facultades = _facultades_de_coordinador(id_personal_coordinador)
    rol_docente = Rol.query.filter_by(nombre='docente_responsable').first()
    if not ids_facultades or not rol_docente:
        return []
    
    filas = db.session.query(Personal.id_personal)\
        .join(ProgramaEstudio, Personal.id_programa == ProgramaEstudio.id_programa)\
        .filter(Personal.id_rol == rol_docente.id_rol,
                ProgramaEstudio.id_facultad.in_(ids_facultades))\
        .distinct().all()
    return [f[0] for f in filas]


def _coordinador_gestiona_a(id_personal_coordinador, id_personal_objetivo):
    return id_personal_objetivo in _ids_personal_gestionado_por_coordinador(id_personal_coordinador)


def _alcance_programas(rol_activo, id_personal):
    """None = alcance global (admin/utsag). Lista = ids de programa permitidos (puede ser vacía)."""
    if rol_activo in ('administrador', 'utsag'):
        return None
    if rol_activo == 'coordinador':
        ids_fac = _facultades_de_coordinador(id_personal)
        if not ids_fac:
            return []
        return [p.id_programa for p in ProgramaEstudio.query.filter(
            ProgramaEstudio.id_facultad.in_(ids_fac)).all()]
    if rol_activo == 'docente_responsable':
        p = Personal.query.get(id_personal)
        if not p or not p.id_programa:
            return []
        return [p.id_programa]
    return []


def _query_respuestas_filtradas(id_encuesta, id_facultad=None, id_programa=None, ids_programas_forzado=None):
    q = Respuesta.query.filter_by(id_encuesta=id_encuesta)
    necesita_join = id_facultad or id_programa or ids_programas_forzado is not None
    if necesita_join:
        q = q.join(Egresado, Respuesta.id_egresado == Egresado.id_egresado)\
             .join(Curricula, Egresado.id_curricula == Curricula.id_curricula)\
             .join(ProgramaEstudio, Curricula.id_programa == ProgramaEstudio.id_programa)
        if ids_programas_forzado is not None:
            q = q.filter(ProgramaEstudio.id_programa.in_(ids_programas_forzado)) if ids_programas_forzado else q.filter(db.literal(False))
        if id_programa:
            q = q.filter(ProgramaEstudio.id_programa == id_programa)
        elif id_facultad:
            q = q.filter(ProgramaEstudio.id_facultad == id_facultad)
    return q

import os
from werkzeug.utils import secure_filename

# Configuración de extensiones permitidas
EXTENSIONES_IMAGEN = {'png', 'jpg', 'jpeg', 'webp'}
EXTENSIONES_DOCUMENTO = {'pdf', 'jpg', 'jpeg', 'png'}

def extension_permitida(nombre_archivo, extensiones):
    """Verifica si la extensión del archivo está dentro del conjunto permitido."""
    return '.' in nombre_archivo and \
           nombre_archivo.rsplit('.', 1)[1].lower() in extensiones

def guardar_archivo(archivo, subcarpeta):
    """Guarda un archivo subido en el directorio uploads correspondiente y retorna su ruta relativa.
    
    Parámetros:
        archivo: Objeto FileStorage recuperado de request.files
        subcarpeta (str): Subdirectorio de destino ('fotos', 'documentos', 'ofertas')
    """
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