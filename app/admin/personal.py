# app/admin/personal.py
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.admin import admin
from app.auth.decorators import requiere_rol
from app.extensions import bcrypt, db
from app.models import Facultad, Personal, ProgramaEstudio, Rol, Usuario

ROLES_ACCESO = ('administrador', 'coordinador')
ROLES_GESTIONABLES = ('coordinador', 'docente_responsable')


def _contexto():
    """Rol del usuario actual y lo que puede asignar: (rol_activo, roles, facultades, programas)."""
    rol_activo = current_user.rol
    if rol_activo == 'administrador':
        roles = Rol.query.filter(Rol.nombre.in_(ROLES_GESTIONABLES)).order_by(Rol.nombre).all()
        facultades = Facultad.query.filter_by(estado='activo').order_by(Facultad.nombre).all()
        programas = (ProgramaEstudio.query.filter_by(estado='activo')
                     .order_by(ProgramaEstudio.nombre).all())
    else:  # coordinador: solo docentes de los programas de su facultad
        id_fac = current_user.personal.id_facultad
        roles = Rol.query.filter_by(nombre='docente_responsable').all()
        facultades = []
        programas = (ProgramaEstudio.query.filter_by(id_facultad=id_fac, estado='activo')
                     .order_by(ProgramaEstudio.nombre).all()) if id_fac else []
    return rol_activo, roles, facultades, programas


def _puede_gestionar(persona):
    """El administrador gestiona a todos; el coordinador, a los docentes de su facultad."""
    if current_user.rol == 'administrador':
        return True
    id_fac = current_user.personal.id_facultad
    return bool(id_fac and persona.programa and persona.programa.id_facultad == id_fac)


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


def _asignar_rol_y_ambito(persona, id_rol, roles, facultades, programas):
    """Valida el rol y su ámbito (facultad o programa) y los asigna. Devuelve un error o None."""
    rol = next((r for r in roles if r.id_rol == id_rol), None)
    if rol is None:
        return 'Selección de rol inválida.'

    if rol.nombre == 'coordinador':
        id_facultad = request.form.get('id_facultad', type=int)
        if not id_facultad:
            return 'Debes seleccionar una facultad para el coordinador.'
        if id_facultad not in {f.id_facultad for f in facultades}:
            return 'Facultad no permitida.'
        persona.id_facultad, persona.id_programa = id_facultad, None
    else:  # docente_responsable
        id_programa = request.form.get('id_programa', type=int)
        if not id_programa:
            return 'Debes seleccionar un programa para el docente responsable.'
        if id_programa not in {p.id_programa for p in programas}:
            return 'No puedes asignar un programa fuera de tu alcance.'
        persona.id_facultad, persona.id_programa = None, id_programa

    persona.id_rol = rol.id_rol
    return persona.validar_ambito()


@admin.route('/admin/personal')
@requiere_rol(*ROLES_ACCESO)
def personal():
    rol_activo = current_user.rol
    q = (db.session.query(Personal, Usuario)
         .join(Usuario, Usuario.id_personal == Personal.id_personal))

    if rol_activo != 'administrador':
        id_fac = current_user.personal.id_facultad
        if not id_fac:
            q = q.filter(db.false())
        else:
            q = (q.join(ProgramaEstudio, Personal.id_programa == ProgramaEstudio.id_programa)
                  .filter(ProgramaEstudio.id_facultad == id_fac))

    lista = q.order_by(Personal.apellido_paterno, Personal.nombres).all()
    return render_template('admin/personal.html', lista=lista, rol_activo=rol_activo)


@admin.route('/admin/personal/nuevo', methods=['GET', 'POST'])
@requiere_rol(*ROLES_ACCESO)
def nuevo_personal():
    rol_activo, roles, facultades, programas = _contexto()

    if rol_activo == 'coordinador' and not programas:
        flash('Tu facultad no tiene programas activos (o no tienes facultad asignada).', 'warning')
        return redirect(url_for('admin.personal'))

    if request.method == 'POST':
        datos = _datos_basicos()
        correo = request.form.get('correo', '').strip()
        contrasena = request.form.get('contrasena', '').strip()

        error = _validar_basicos(datos)
        if not error and not correo:
            error = 'El correo es obligatorio.'
        if not error and Usuario.query.filter_by(correo=correo).first():
            error = 'Ese correo ya está registrado.'
        if not error and len(contrasena) < 8:
            error = 'La contraseña debe tener al menos 8 caracteres.'

        persona = None
        if not error:
            persona = Personal(**datos)
            error = _asignar_rol_y_ambito(persona, request.form.get('id_rol', type=int),
                                          roles, facultades, programas)
        if error:
            flash(error, 'warning')
            return redirect(url_for('admin.nuevo_personal'))

        db.session.add(persona)
        db.session.flush()
        db.session.add(Usuario(
            correo=correo,
            contrasena_hash=bcrypt.generate_password_hash(contrasena).decode('utf-8'),
            id_personal=persona.id_personal,
            estado='activo'))
        db.session.commit()

        flash('Cuenta de personal creada correctamente.', 'success')
        return redirect(url_for('admin.personal'))

    return render_template('admin/nuevo_personal.html',
        roles=roles, facultades=facultades, programas=programas, rol_activo=rol_activo)


@admin.route('/admin/personal/<int:id>/editar', methods=['GET', 'POST'])
@requiere_rol(*ROLES_ACCESO)
def editar_personal(id):
    persona = db.get_or_404(Personal, id)
    usuario = Usuario.query.filter_by(id_personal=id).first_or_404()
    rol_activo, roles, facultades, programas = _contexto()

    if not _puede_gestionar(persona):
        flash('No tienes permisos sobre esta cuenta.', 'danger')
        return redirect(url_for('admin.personal'))

    # Las cuentas administrador solo permiten editar datos y contraseña, no el rol
    puede_cambiar_rol = persona.rol.nombre in ROLES_GESTIONABLES

    if request.method == 'POST':
        datos = _datos_basicos()
        nueva_clave = request.form.get('nueva_contrasena', '').strip()

        error = _validar_basicos(datos, excluir_id=id)
        if not error and nueva_clave and len(nueva_clave) < 8:
            error = 'La nueva contraseña debe tener al menos 8 caracteres.'
        if not error:
            for campo, valor in datos.items():
                setattr(persona, campo, valor)
            if puede_cambiar_rol:
                error = _asignar_rol_y_ambito(persona, request.form.get('id_rol', type=int),
                                              roles, facultades, programas)
        if error:
            db.session.rollback()
            flash(error, 'warning')
            return redirect(url_for('admin.editar_personal', id=id))

        if nueva_clave:
            usuario.contrasena_hash = bcrypt.generate_password_hash(nueva_clave).decode('utf-8')
        db.session.commit()
        flash('Datos actualizados correctamente.', 'success')
        return redirect(url_for('admin.personal'))

    return render_template('admin/editar_personal.html',
        persona=persona, usuario=usuario, roles=roles, facultades=facultades,
        programas=programas, rol_activo=rol_activo, puede_cambiar_rol=puede_cambiar_rol)


@admin.route('/admin/personal/<int:id>/toggle', methods=['POST'])
@requiere_rol(*ROLES_ACCESO)
def toggle_personal(id):
    persona = db.get_or_404(Personal, id)
    usuario = Usuario.query.filter_by(id_personal=id).first_or_404()

    if persona.id_personal == current_user.id_personal:
        flash('No puedes desactivar tu propia cuenta.', 'danger')
    elif persona.id_personal == 1:
        flash('La cuenta administradora nativa no puede desactivarse.', 'danger')
    elif not _puede_gestionar(persona):
        flash('No tienes permiso sobre esta cuenta.', 'danger')
    else:
        usuario.estado = 'inactivo' if usuario.estado == 'activo' else 'activo'
        db.session.commit()
        flash(f'Cuenta {"activada" if usuario.estado == "activo" else "desactivada"}.', 'info')

    return redirect(url_for('admin.personal'))