# app/admin/ofertas.py
import os
import uuid
from datetime import date

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from app.admin import admin
from app.auth.decorators import requiere_rol
from app.extensions import db
from app.models import OfertaLaboral, Sector
from app.utils.historial import registrar
from app.utils.helpers import borrar_archivo

ROLES = ('administrador', 'coordinador')
EXT_IMAGEN = {'png', 'jpg', 'jpeg', 'webp'}


def _guardar_imagen(archivo):
    """Guarda la imagen en instance/uploads/ofertas y devuelve la ruta relativa."""
    nombre = archivo.filename or ''
    ext = nombre.rsplit('.', 1)[-1].lower() if '.' in nombre else ''
    if ext not in EXT_IMAGEN:
        return None
    # Cambiado a instance_path
    carpeta = os.path.join(current_app.instance_path, 'uploads', 'ofertas')
    os.makedirs(carpeta, exist_ok=True)
    archivo_final = f'{uuid.uuid4().hex}.{ext}'
    archivo.save(os.path.join(carpeta, archivo_final))
    return f'uploads/ofertas/{archivo_final}'


def _leer_formulario():
    """Devuelve (datos, error). Si error no es None, no se debe guardar."""
    f = request.form

    def txt(campo):
        return f.get(campo, '').strip() or None

    try:
        vencimiento = date.fromisoformat(f.get('fecha_vencimiento', ''))
    except ValueError:
        vencimiento = None

    datos = {
        'titulo':            txt('titulo'),
        'empresa_nombre':    txt('empresa_nombre'),
        'id_sector':         f.get('id_sector', type=int),
        'contacto_telefono': txt('contacto_telefono'),
        'tipo_oferta':       txt('tipo_oferta') or 'Empleo',
        'descripcion':       txt('descripcion'),
        'requisitos':        txt('requisitos'),
        'funciones':         txt('funciones'),
        'modalidad':         txt('modalidad'),
        'jornada':           txt('jornada'),
        'remuneracion':      txt('remuneracion'),
        'ubicacion':         txt('ubicacion'),
        'url_original':      txt('url_original'),
        'fecha_vencimiento': vencimiento,
    }
    if not (datos['titulo'] and datos['empresa_nombre'] and vencimiento):
        return datos, 'Completa el título, la empresa y la fecha de vencimiento.'
    return datos, None


@admin.route('/admin/ofertas')
@requiere_rol(*ROLES)
def ofertas():
    buscar = request.args.get('buscar', '').strip()
    pagina = request.args.get('pagina', 1, type=int)
    estado = request.args.get('estado', 'activa')

    # Desactivar ofertas vencidas
    OfertaLaboral.query.filter(
        OfertaLaboral.fecha_vencimiento < date.today(),
        OfertaLaboral.activa == True
    ).update({'activa': False})
    db.session.commit()

    q = OfertaLaboral.query.filter_by(activa=(estado == 'activa'))
    if buscar:
        like = f'%{buscar}%'
        q = q.filter(or_(
            OfertaLaboral.titulo.ilike(like),
            OfertaLaboral.empresa_nombre.ilike(like),
            OfertaLaboral.ubicacion.ilike(like),
        ))

    paginado = (q.order_by(OfertaLaboral.fecha_publicacion.desc())
                 .paginate(page=pagina, per_page=15, error_out=False))

    ultima = (OfertaLaboral.query.filter_by(fuente='automatico')
              .order_by(OfertaLaboral.fecha_publicacion.desc()).first())

    return render_template('admin/ofertas.html',
        ofertas=paginado.items, paginacion=paginado, buscar=buscar,
        estado=estado, pagina=pagina,
        ultima_sync=ultima.fecha_publicacion if ultima else None)


@admin.route('/admin/ofertas/nueva', methods=['GET', 'POST'])
@requiere_rol(*ROLES)
def nueva_oferta():
    if request.method == 'POST':
        datos, error = _leer_formulario()
        if error:
            flash(error, 'danger')
        else:
            oferta = OfertaLaboral(
                **datos,
                id_creado_por=current_user.id_personal,
                fuente='manual',
                fecha_publicacion=date.today(),
                activa=True)
            imagen = request.files.get('imagen')
            if imagen and imagen.filename:
                oferta.ruta_imagen = _guardar_imagen(imagen)

            # Historial auditoria
            registrar('creacion', 'ofertas', f'Publicó la oferta "{oferta.titulo}" ({oferta.empresa_nombre})')

            db.session.add(oferta)
            db.session.commit()
            flash('Oferta publicada correctamente.', 'success')
            return redirect(url_for('admin.ofertas'))

    sectores = Sector.query.order_by(Sector.nombre).all()
    return render_template('admin/nueva_oferta.html', sectores=sectores)


@admin.route('/admin/ofertas/<int:id>/editar', methods=['GET', 'POST'])
@requiere_rol(*ROLES)
def editar_oferta(id):
    oferta = db.get_or_404(OfertaLaboral, id)

    if request.method == 'POST':
        datos, error = _leer_formulario()
        if error:
            flash(error, 'danger')
        else:
            for campo, valor in datos.items():
                setattr(oferta, campo, valor)
            oferta.activa = bool(request.form.get('activa'))

            anterior = oferta.ruta_imagen
            nueva = None
            imagen = request.files.get('imagen')
            
            if imagen and imagen.filename:
                nueva = _guardar_imagen(imagen)
                if nueva:
                    oferta.ruta_imagen = nueva

            # Historial auditoría
            registrar('actualizacion', 'ofertas', f'Actualizó la oferta "{oferta.titulo}"')

            db.session.commit()
            
            # Borrar la imagen anterior solo después del commit exitoso
            if nueva and anterior:
                borrar_archivo(anterior)

            flash('Oferta actualizada.', 'success')
            return redirect(url_for('admin.ofertas'))

    sectores = Sector.query.order_by(Sector.nombre).all()
    return render_template('admin/editar_oferta.html', oferta=oferta, sectores=sectores)


@admin.route('/admin/ofertas/<int:id>/toggle', methods=['POST'])
@requiere_rol(*ROLES)
def toggle_oferta(id):
    oferta = db.get_or_404(OfertaLaboral, id)
    oferta.activa = not oferta.activa

    # Historial auditoria
    registrar('actualizacion', 'ofertas', f'{"Activó" if oferta.activa else "Desactivó"} la oferta "{oferta.titulo}"')

    db.session.commit()
    flash(f'Oferta {"activada" if oferta.activa else "desactivada"}.', 'info')
    return redirect(url_for('admin.ofertas',
        estado=request.form.get('estado', 'activa'),
        pagina=request.form.get('pagina', 1)))





@admin.route('/admin/ofertas/<int:id>/eliminar', methods=['POST'])
@requiere_rol(*ROLES)
def eliminar_oferta(id):
    oferta = db.get_or_404(OfertaLaboral, id)
    if oferta.fuente != 'manual':
        flash('Solo se pueden eliminar las ofertas publicadas manualmente. Las automáticas se retiran solas al vencer.', 'warning')
    else:
        registrar('eliminacion', 'ofertas', f'Eliminó la oferta "{oferta.titulo}" ({oferta.empresa_nombre})')
        imagen = oferta.ruta_imagen
        db.session.delete(oferta)
        db.session.commit()
        borrar_archivo(imagen)
        flash('Oferta eliminada.', 'info')
    return redirect(url_for('admin.ofertas',
        estado=request.form.get('estado', 'activa'),
        pagina=request.form.get('pagina', 1)))