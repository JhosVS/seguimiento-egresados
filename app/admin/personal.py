# app/admin/personal.py
import re

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from app.admin import admin
from app.auth.decorators import requiere_rol
from app.extensions import bcrypt, db
from app.models import Personal, Rol, Usuario
from app.admin.roles import ROLES_HABILITADOS

from app.utils.historial import registrar
from app.models import Historial
from app.utils.historial import depurar_historial


# Helpers
def _datos_basicos():
    f = request.form
    return {
        'dni':              f.get('dni', '').strip() or None,
        'nombres':          f.get('nombres', '').strip(),
        'apellido_paterno': f.get('apellido_paterno', '').strip(),
        'apellido_materno': f.get('apellido_materno', '').strip() or None,
        'telefono':         f.get('telefono', '').strip() or None,
    }

def _validar_basicos(datos, excluir_id=None):
    if not datos['nombres'] or not datos['apellido_paterno']:
        return 'Completa los nombres y el apellido paterno.'
    dni = datos['dni']
    if dni:
        if not (dni.isdigit() and len(dni) == 8):
            return 'El DNI debe tener 8 dígitos.'
        q = Personal.query.filter_by(dni=dni)
        if excluir_id:
            q = q.filter(Personal.id_personal != excluir_id)
        if q.first():
            return 'Ese DNI ya está registrado.'
    return None

def _error_correo(correo):
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', correo) or len(correo) > 150:
        return 'El correo no es válido.'
    return None

def _error_contrasena(clave):
    """Mismas reglas que el registro del egresado."""
    if not 8 <= len(clave) <= 72 or not re.search(r'[A-Za-z]', clave) or not re.search(r'\d', clave):
        return 'La contraseña debe tener entre 8 y 72 caracteres, con letras y números.'
    return None

def _administradores_activos():
    return (db.session.query(Usuario)
            .join(Personal, Usuario.id_personal == Personal.id_personal)
            .join(Rol, Personal.id_rol == Rol.id_rol)
            .filter(Rol.nombre == 'administrador', Usuario.estado == 'activo').count())

# FUNCIONALIDADES
@admin.route('/admin/personal')
@requiere_rol('administrador')
def personal():
    lista = (db.session.query(Personal, Usuario)
             .join(Usuario, Usuario.id_personal == Personal.id_personal)
             .order_by(Personal.apellido_paterno, Personal.nombres).all())
    return render_template('admin/personal.html', lista=lista, roles_habilitados=ROLES_HABILITADOS)


@admin.route('/admin/personal/nuevo', methods=['GET', 'POST'])
@requiere_rol('administrador')
def nuevo_personal():
    if request.method == 'POST':
        datos = _datos_basicos()
        correo = request.form.get('correo', '').strip().lower()   # el login compara en minúsculas
        contrasena = request.form.get('contrasena', '')

        error = _validar_basicos(datos) or _error_correo(correo) or _error_contrasena(contrasena)
        if not error and Usuario.query.filter_by(correo=correo).first():
            error = 'Ese correo ya está registrado.'

        # El rol NO viene del formulario: toda cuenta de personal nueva es administrador
        rol = Rol.query.filter_by(nombre=ROLES_HABILITADOS[0]).first()
        if not error and rol is None:
            error = 'No existe el rol administrador en la base de datos.'

        if error:
            flash(error, 'warning')
            return render_template('admin/formulario_personal.html', persona=None, datos=request.form)

        persona = Personal(**datos, id_rol=rol.id_rol)
        db.session.add(persona)
        db.session.flush()
        db.session.add(Usuario(
            correo=correo,
            contrasena_hash=bcrypt.generate_password_hash(contrasena).decode('utf-8'),
            id_personal=persona.id_personal,
            estado='activo'))

        # Se registra la acción cuando se crea un nuevo personal
        registrar('creacion', 'personal', f'Creó la cuenta de administrador {correo}')
        
        db.session.commit()

        flash('Cuenta de administrador creada correctamente.', 'success')
        return redirect(url_for('admin.personal'))

    return render_template('admin/formulario_personal.html', persona=None, datos=None)


@admin.route('/admin/personal/<int:id>/editar', methods=['GET', 'POST'])
@requiere_rol('administrador')
def editar_personal(id):
    persona = db.get_or_404(Personal, id)
    usuario = Usuario.query.filter_by(id_personal=id).first_or_404()

    if request.method == 'POST':
        datos = _datos_basicos()
        nueva_clave = request.form.get('nueva_contrasena', '')

        error = _validar_basicos(datos, excluir_id=id)
        if not error and nueva_clave:
            error = _error_contrasena(nueva_clave)
        if error:
            flash(error, 'warning')
            return render_template('admin/formulario_personal.html', persona=persona, datos=request.form)

        for campo, valor in datos.items():
            setattr(persona, campo, valor)
        if nueva_clave:
            usuario.contrasena_hash = bcrypt.generate_password_hash(nueva_clave).decode('utf-8')
            usuario.ultimo_cambio_password = func.now() if persona.id_personal == current_user.id_personal else None

        # Se registra la acción cada que se edita un personal
        registrar('actualizacion', 'personal', f'Actualizó la cuenta de {usuario.correo}' + (' (cambió la contraseña)' if nueva_clave else ''))

        db.session.commit()
        flash('Datos actualizados correctamente.', 'success')
        return redirect(url_for('admin.personal'))

    return render_template('admin/formulario_personal.html', persona=persona, datos=None)


@admin.route('/admin/personal/<int:id>/toggle', methods=['POST'])
@requiere_rol('administrador')
def toggle_personal(id):
    persona = db.get_or_404(Personal, id)
    usuario = Usuario.query.filter_by(id_personal=id).first_or_404()

    if persona.id_personal == current_user.id_personal:
        flash('No puedes desactivar tu propia cuenta.', 'danger')
    elif (usuario.estado == 'activo' and persona.rol.nombre in ROLES_HABILITADOS
          and _administradores_activos() <= 1):
        flash('Debe existir al menos un administrador activo.', 'danger')
    else:
        registrar('actualizacion', 'personal',
                  f'{"Activó" if usuario.estado == "inactivo" else "Desactivó"} la cuenta de {usuario.correo}')
        usuario.estado = 'inactivo' if usuario.estado == 'activo' else 'activo'
        db.session.commit()
        flash(f'Cuenta {"activada" if usuario.estado == "activo" else "desactivada"}.', 'info')

    return redirect(url_for('admin.personal'))

# ==============================================
# Apartado de Historial (Auditoria)
# ==============================================

@admin.route('/admin/historial')
@requiere_rol('administrador')
def historial():
    depurar_historial()           # por si el servidor estuvo apagado a la hora programada
    accion = request.args.get('accion', '')
    texto = request.args.get('q', '').strip()

    # 1. Obtenemos los IDs de los 40 registros más recientes en general (100% compatible con MySQL/SQLite)
    ultimos_ids = [h.id_historial for h in Historial.query.with_entities(Historial.id_historial).order_by(Historial.fecha.desc()).limit(40).all()]

    # 2. Base de la consulta filtrada solo sobre esos 40 registros tope
    q = Historial.query.filter(Historial.id_historial.in_(ultimos_ids)) if ultimos_ids else Historial.query.filter(db.text('0=1'))

    if accion:
        q = q.filter(Historial.accion == accion)
    if texto:
        q = q.filter(db.or_(Historial.usuario_correo.ilike(f'%{texto}%'),
                            Historial.detalle.ilike(f'%{texto}%'),
                            Historial.modulo.ilike(f'%{texto}%')))
                            
    pagina = q.order_by(Historial.fecha.desc()).paginate(
        page=request.args.get('page', 1, type=int), per_page=40, error_out=False)
        
    return render_template('admin/historial.html', pagina=pagina, accion=accion, texto=texto)