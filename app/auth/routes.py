# app/auth/routes.py
import os
from flask import render_template, redirect, url_for, flash, request, session, current_app, send_from_directory, abort, current_app

import hashlib
import re
import secrets
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.auth import auth
from app.auth.forms import (LoginForm, VerificarForm, RegistroForm, RecuperarForm, NuevaContrasenaForm, CambiarContrasenaForm)
from app.extensions import db, bcrypt
from app.models import Usuario, Egresado, ProgramaEstudio, Curricula, Certificado
# from app.models import Facultad   # solo para el modo multi-programa (ver _resolver_curricula)
from app.utils.api_undac import consultar_api_undac
from app.utils.email import enviar_correo_recuperacion
from app.admin.roles import ROLES_HABILITADOS
from app.utils.historial import registrar, estado_acceso, MAX_INTENTOS, MINUTOS_BLOQUEO

# Campos del formulario de registro que se copian al egresado
CAMPOS_PERFIL = ['nombres', 'apellido_paterno', 'apellido_materno',
                 'genero', 'fecha_nacimiento', 'telefono', 'correo_personal',
                 'region', 'provincia', 'distrito', 'domicilio',
                 'anio_ingreso', 'anio_egreso']

# Programas que pueden registrarse (nombre exacto de la API).
# Para abrir más programas: agregarlos aquí y activar el bloque comentado
# de _resolver_curricula.
PROGRAMAS_PERMITIDOS = {'Ingeniería de Sistemas y Computación'}


# ------------------------------------------------------------
# Funciones de apoyo
# ------------------------------------------------------------
def _hash_password(texto):
    return bcrypt.generate_password_hash(texto).decode('utf-8')


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _normalizar(texto):
    """Quita espacios y unifica tildes (la API a veces las manda descompuestas)."""
    return unicodedata.normalize('NFC', (texto or '').strip())


def url_destino_usuario(usuario):
    """Egresado -> su perfil. Cualquier otro (personal) -> panel admin."""
    if usuario.es_egresado:
        return url_for('egresado.perfil')
    return url_for('admin.dashboard')


def _next_seguro():
    """Usa ?next= solo si es una ruta interna (evita redirigir a otros sitios)."""
    destino = request.args.get('next', '')
    if (destino.startswith('/') and not destino.startswith('//')
            and '\\' not in destino and not urlparse(destino).netloc):
        return destino
    return None

def _modo_pruebas():
    """Se activa con MODO_PRUEBAS=1 en el .env. Solo para sesiones de prueba."""
    return os.getenv('MODO_PRUEBAS') == '1'


def _datos_de_prueba(dni):
    """Lo que devolvería la API, inventado: todos quedan en la misma currícula de prueba."""
    return {
        'Dni': dni,
        'Rol': 'EG',
        'Programa facultad': sorted(PROGRAMAS_PERMITIDOS)[0],
        'Curricula': os.getenv('CURRICULA_PRUEBAS', '17A4SI'),
    }

def _validar_api(codigo, dni):
    """
    Consulta la API y comprueba que la persona pueda registrarse.
    Devuelve (datos, None) si puede, o (None, (mensaje, categoria)) si no.
    """
    if _modo_pruebas():
        current_app.logger.warning('MODO_PRUEBAS activo: no se consultó la API de la UNDAC.')
        return _datos_de_prueba(dni), None

    datos = consultar_api_undac(codigo)
    if not datos or datos.get('Dni') != dni:
        # Mismo mensaje si el código no existe o el DNI no coincide
        return None, ('No se encontró un egresado con ese código y DNI. '
                      'Si el problema continúa, inténtalo más tarde.', 'danger')
    if datos.get('Rol') != 'EG':
        return None, ('Solo pueden registrarse egresados.', 'warning')
    if _normalizar(datos.get('Programa facultad')) not in PROGRAMAS_PERMITIDOS:
        return None, ('Por ahora el registro solo está habilitado para egresados de '
                      + ', '.join(sorted(PROGRAMAS_PERMITIDOS)) + '.', 'warning')
    return datos, None


def _buscar_egresado(codigo, dni):
    return Egresado.query.filter(
        (Egresado.codigo_universitario == codigo) | (Egresado.dni == dni)).first()


def _resolver_curricula(datos):
    """
    Devuelve la currícula del egresado o None si no se puede determinar.
    Si la currícula no existe la crea (ej. '17A4SI' -> año 2017), siempre que
    su programa ya exista en la base. No hace commit: lo hace quien la llama.
    """
    nombre = (datos.get('Curricula') or '').strip()
    curricula = Curricula.query.filter_by(nombre=nombre).first()
    if curricula:
        return curricula

    m = re.match(r'(\d{2})A', nombre.upper())
    programa = ProgramaEstudio.query.filter_by(
        nombre=_normalizar(datos.get('Programa facultad'))).first()

    if not m or not programa:
        return None

    curricula = Curricula(id_programa=programa.id_programa, nombre=nombre,
                          anio_inicio=2000 + int(m.group(1)))
    db.session.add(curricula)
    db.session.flush()
    return curricula


# ------------------------------------------------------------
# Login y logout
# ------------------------------------------------------------
@auth.route('/login', methods=['GET', 'POST'], strict_slashes=False)
def login():
    if current_user.is_authenticated:
        return redirect(url_destino_usuario(current_user))

    form = LoginForm()
    if form.validate_on_submit():
        correo = form.correo.data.lower()
        bloqueado, fallos = estado_acceso(correo)
        if bloqueado:
            flash(f'Demasiados intentos fallidos. Espera {MINUTOS_BLOQUEO} minutos e inténtalo de nuevo.', 'danger')
            return render_template('auth/login.html', form=form)

        usuario = Usuario.query.filter_by(correo=correo).first()
        motivo = None
        if not usuario or not bcrypt.check_password_hash(usuario.contrasena_hash, form.contrasena.data):
            motivo = 'Correo o contraseña incorrectos'
            flash('Correo o contraseña incorrectos.', 'danger')
        elif not usuario.is_active:
            motivo = 'Cuenta inactiva'
            flash('Tu cuenta está inactiva. Contacta con soporte.', 'danger')
        elif usuario.es_personal and usuario.rol not in ROLES_HABILITADOS:
            motivo = 'Rol no habilitado'
            flash('Tu rol aún no está habilitado en el sistema. Contacta con el administrador.', 'warning')
        else:
            login_user(usuario)
            session.permanent = True
            registrar('inicio_sesion', 'acceso', 'Inició sesión')
            usuario.ultimo_acceso = func.now()
            db.session.commit()
            return redirect(_next_seguro() or url_destino_usuario(usuario))

        if fallos + 1 >= MAX_INTENTOS:
            motivo += f' (cuenta bloqueada {MINUTOS_BLOQUEO} minutos)'
        registrar('intento_fallido', 'acceso', motivo, guardar=True, correo=correo)

    return render_template('auth/login.html', form=form)


@auth.route('/logout', strict_slashes=False)
@login_required
def logout():
    logout_user()
    session.permanent = True
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('auth.login'))


# ------------------------------------------------------------
# Registro de egresados
# ------------------------------------------------------------
@auth.route('/verificar', methods=['GET', 'POST'], strict_slashes=False)
def verificar():
    """Paso 1: código universitario + DNI, comprobados con la API de la UNDAC."""
    if current_user.is_authenticated:
        return redirect(url_destino_usuario(current_user))

    form = VerificarForm()
    if form.validate_on_submit():
        codigo, dni = form.codigo_universitario.data, form.dni.data
        _, aviso = _validar_api(codigo, dni)

        if aviso:
            flash(*aviso)
        else:
            egresado = _buscar_egresado(codigo, dni)
            if egresado and egresado.usuario:
                flash('Usted ya está registrado. Inicie sesión.', 'info')
                return redirect(url_for('auth.login'))

            session['reg_temp'] = {'codigo': codigo, 'dni': dni}   # solo lo mínimo
            return redirect(url_for('auth.registro'))

    return render_template('auth/verificar.html', form=form, modo_pruebas=_modo_pruebas())


@auth.route('/registro', methods=['GET', 'POST'], strict_slashes=False)
def registro():
    """
    Paso 2: el egresado escribe sus nombres y datos, su correo de acceso,
    crea su contraseña y da su consentimiento.
    De la API solo salen solos: DNI, código y currícula (con su programa).
    """
    if current_user.is_authenticated:
        return redirect(url_destino_usuario(current_user))

    temp = session.get('reg_temp')
    if not temp:
        flash('Primero verifica tu código universitario y DNI.', 'warning')
        return redirect(url_for('auth.verificar'))

    # Se vuelve a consultar la API; la sesión solo guarda código y DNI
    datos, aviso = _validar_api(temp['codigo'], temp['dni'])
    if aviso:
        session.pop('reg_temp', None)
        flash(*aviso)
        return redirect(url_for('auth.verificar'))

    form = RegistroForm()
    if form.validate_on_submit():
        correo = form.correo.data.lower()

        if Usuario.query.filter_by(correo=correo).first():
            flash('Ese correo ya está en uso por otra cuenta.', 'danger')
        else:
            try:
                curricula = _resolver_curricula(datos)
                if curricula is None:
                    db.session.rollback()
                    flash('Tu currícula aún no está habilitada. Contacta con soporte.', 'danger')
                    return redirect(url_for('auth.verificar'))

                egresado = (_buscar_egresado(temp['codigo'], temp['dni'])
                            or Egresado(codigo_universitario=temp['codigo'], dni=temp['dni'],
                                        id_curricula=curricula.id_curricula))
                for campo in CAMPOS_PERFIL:
                    setattr(egresado, campo, getattr(form, campo).data or None)
                egresado.acepta_tratamiento_datos = True
                egresado.fecha_consentimiento = func.now()
                db.session.add(egresado)
                db.session.flush()                        # obtiene id_egresado

                db.session.add(Usuario(
                    correo=correo,
                    contrasena_hash=_hash_password(form.contrasena.data),
                    id_egresado=egresado.id_egresado,
                    ultimo_cambio_password=func.now()))
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('No se pudo crear la cuenta. Es posible que ya exista; intenta iniciar sesión.', 'danger')
                return redirect(url_for('auth.login'))

            session.pop('reg_temp', None)
            flash('¡Cuenta creada! Inicia sesión con el correo que registraste.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/registro.html', form=form, codigo=temp['codigo'], modo_pruebas=_modo_pruebas())


# ------------------------------------------------------------
# Contraseñas
# ------------------------------------------------------------
@auth.route('/recuperar', methods=['GET', 'POST'], strict_slashes=False)
def recuperar_contrasena():
    if current_user.is_authenticated:
        return redirect(url_destino_usuario(current_user))

    form = RecuperarForm()
    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(correo=form.correo.data.lower()).first()
        if usuario and usuario.is_active:
            token = secrets.token_urlsafe(32)
            usuario.token_recuperacion_hash = _hash_token(token)   # en la BD solo el hash
            usuario.token_expiracion = datetime.now() + timedelta(minutes=30)
            db.session.commit()
            enviar_correo_recuperacion(usuario.correo, token)

        # Mismo mensaje exista o no el correo
        flash('Si el correo está registrado, recibirás un enlace en unos minutos.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/recuperar_contrasena.html', form=form)


@auth.route('/restablecer/<token>', methods=['GET', 'POST'], strict_slashes=False)
def restablecer_contrasena(token):
    usuario = Usuario.query.filter_by(token_recuperacion_hash=_hash_token(token)).first()
    if (not usuario or not usuario.is_active
            or not usuario.token_expiracion or usuario.token_expiracion < datetime.now()):
        flash('El enlace no es válido o ya venció. Solicita uno nuevo.', 'danger')
        return redirect(url_for('auth.recuperar_contrasena'))

    form = NuevaContrasenaForm()
    if form.validate_on_submit():
        usuario.contrasena_hash = _hash_password(form.contrasena.data)
        usuario.token_recuperacion_hash = None          # el enlace sirve una sola vez
        usuario.token_expiracion = None
        usuario.ultimo_cambio_password = func.now()
        db.session.commit()
        flash('Contraseña actualizada. Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/restablecer_contrasena.html', form=form)


@auth.route('/cambiar-contrasena', methods=['GET', 'POST'], strict_slashes=False)
@login_required
def cambiar_contrasena():
    form = CambiarContrasenaForm()
    if form.validate_on_submit():
        if not bcrypt.check_password_hash(current_user.contrasena_hash, form.contrasena_actual.data):
            flash('La contraseña actual no es correcta.', 'danger')
        elif form.contrasena.data == form.contrasena_actual.data:
            flash('La nueva contraseña debe ser distinta de la actual.', 'warning')
        else:
            current_user.contrasena_hash = _hash_password(form.contrasena.data)
            current_user.ultimo_cambio_password = func.now()
            registrar('actualizacion', 'cuenta', 'Cambió su contraseña')
            db.session.commit()
            flash('Contraseña actualizada correctamente.', 'success')
            return redirect(url_destino_usuario(current_user))

    return render_template('auth/cambiar_contrasena.html', form=form)

# ------------------------------------------------------------
# PDF de certificados (los ve su dueño o el personal)
# ------------------------------------------------------------
@auth.route('/certificados/<int:id>/archivo')
@login_required
def archivo_certificado(id):
    cert = db.session.get(Certificado, id)
    if cert is None or not cert.ruta_archivo:
        abort(404)
    if not (current_user.es_personal or cert.id_egresado == current_user.id_egresado):
        abort(403)

    if current_user.es_personal:     # el dueño viendo su propio PDF no se registra
        registrar('consulta', 'formacion_complementaria', f'Abrió el PDF de "{cert.nombre}" de {cert.egresado.nombre_completo}', guardar=True)

    carpeta = os.path.join(current_app.instance_path, 'certificados')
    return send_from_directory(carpeta, os.path.basename(cert.ruta_archivo), mimetype='application/pdf', download_name=f'certificado-{cert.id_certificado}.pdf')