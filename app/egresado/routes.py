# app/egresado/routes.py
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import render_template, redirect, url_for, flash, request, send_file, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.egresado import egresado
from app.extensions import db
from app.models import (
    Egresado, Empleo, Usuario, FormacionAcademica,
    Certificado, Habilidad, Sector,
    Encuesta, EncuestaEnvio, Pregunta, Respuesta, RespuestaOpcion
)

# ============================================
# UTILIDADES Y DECORADORES
# ============================================

def solo_egresado(f):
    @wraps(f)
    def decorado(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.es_egresado:
            flash('Acceso no permitido.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorado

# ============================================
# PERFIL
# ============================================

@egresado.route('/perfil')
@login_required
@solo_egresado
def perfil():
    e = Egresado.query.get(current_user.id_egresado)
    return render_template('egresado/perfil.html', e=e)


@egresado.route('/perfil/editar', methods=['GET', 'POST'])
@login_required
@solo_egresado
def editar_perfil():
    e = Egresado.query.get(current_user.id_egresado)

    if request.method == 'POST':
        correo_inst = request.form.get('correo_institucional', '').strip()
        if correo_inst and correo_inst != current_user.correo:
            existe = Usuario.query.filter(
                Usuario.correo == correo_inst,
                Usuario.id_usuario != current_user.id_usuario
            ).first()
            if existe:
                flash('Ese correo ya está en uso por otra cuenta.', 'danger')
                return render_template('egresado/editar_perfil.html', e=e)
            current_user.correo = correo_inst

        e.correo_personal = request.form.get('correo_personal', '').strip()
        e.telefono        = request.form.get('telefono', '').strip()
        e.distrito        = request.form.get('distrito', '').strip()
        e.provincia       = request.form.get('provincia', '').strip()
        e.region          = request.form.get('region', '').strip()
        e.pais            = request.form.get('pais', '').strip() or 'Perú'
        e.linkedin        = request.form.get('linkedin', '').strip()
        e.facebook        = request.form.get('facebook', '').strip()
        e.tiktok          = request.form.get('tiktok', '').strip()
        e.nombres = request.form.get('nombres', '').strip() or e.nombres
        e.apellido_paterno = request.form.get('apellido_paterno', '').strip() or e.apellido_paterno
        e.apellido_materno = request.form.get('apellido_materno', '').strip() or None
        genero = request.form.get('genero', '')
        if genero in ('M', 'F'):
            e.genero = genero

        anio_ingreso = request.form.get('anio_ingreso', '').strip()
        if anio_ingreso and anio_ingreso.isdigit():
            e.anio_ingreso = int(anio_ingreso)

        anio_egreso = request.form.get('anio_egreso', '').strip()
        if anio_egreso:
            try:
                anio_egreso_int = int(anio_egreso)
                if 1990 <= anio_egreso_int <= 2100:
                    e.anio_egreso = anio_egreso_int
            except ValueError:
                pass

        periodo = request.form.get('periodo_egreso', '').strip().upper()
        e.periodo_egreso = periodo[:10] or None

        foto = request.files.get('foto')
        if foto and foto.filename:
            from app.utils.helpers import guardar_archivo
            ruta = guardar_archivo(foto, 'fotos')
            if ruta:
                e.foto = ruta
            else:
                flash('Formato de foto no permitido. Usa PNG, JPG o WEBP.', 'warning')

        db.session.commit()
        flash('Perfil actualizado correctamente.', 'success')
        return redirect(url_for('egresado.perfil'))

    habilidades_l = Habilidad.query.filter_by(id_egresado=e.id_egresado, tipo='habilidad').all()
    intereses_l   = Habilidad.query.filter_by(id_egresado=e.id_egresado, tipo='interes').all()
    return render_template('egresado/editar_perfil.html', e=e, habilidades=habilidades_l, intereses=intereses_l)


# ============================================
# EMPLEOS
# ============================================

@egresado.route('/empleos')
@login_required
@solo_egresado
def empleos():
    lista = Empleo.query.filter_by(id_egresado=current_user.id_egresado)\
                         .order_by(Empleo.fecha_fin.is_(None).desc(), Empleo.fecha_inicio.desc()).all()
    return render_template('egresado/empleos.html', empleos=lista)


from datetime import datetime
@egresado.route('/empleos/nuevo', methods=['GET', 'POST'])
@login_required
@solo_egresado
def nuevo_empleo():
    egresado = current_user.egresado

    if request.method == 'POST':
        id_sector_val = request.form.get('id_sector')
        id_sector = int(id_sector_val) if id_sector_val else None

        es_actual = request.form.get('es_actual') == 'on'
        
        f_inicio_str = request.form.get('fecha_inicio')
        f_fin_str = request.form.get('fecha_fin')

        # Convertir YYYY-MM a objeto Date
        fecha_inicio = datetime.strptime(f_inicio_str, '%Y-%m').date() if f_inicio_str else None
        fecha_fin = None if es_actual or not f_fin_str else datetime.strptime(f_fin_str, '%Y-%m').date()

        empleo = Empleo(
            id_egresado=egresado.id_egresado,
            empresa_nombre=request.form.get('empresa_nombre'),
            id_sector=id_sector,
            cargo=request.form.get('cargo'),
            tipo_contrato=request.form.get('tipo_contrato'),
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            funciones=request.form.get('funciones')
        )
        
        db.session.add(empleo)
        db.session.commit()

        flash(f'Empleo en "{empleo.empresa_nombre}" registrado. Puedes agregar el siguiente.', 'success')
        return redirect(url_for('egresado.nuevo_empleo'))

    sectores = Sector.query.all()
    return render_template('egresado/nuevo_empleo.html', sectores=sectores)


@egresado.route('/empleos/<int:id>/eliminar', methods=['POST'])
@login_required
@solo_egresado
def eliminar_empleo(id):
    empleo = Empleo.query.get_or_404(id)
    if empleo.id_egresado != current_user.id_egresado:
        flash('No tienes permiso para eliminar este empleo.', 'danger')
        return redirect(url_for('egresado.empleos'))

    db.session.delete(empleo)
    db.session.commit()
    flash('Empleo eliminado.', 'info')
    return redirect(url_for('egresado.empleos'))


# ============================================
# FORMACIÓN PROFESIONAL (TITULOS Y GRADOS)
# ============================================

@egresado.route('/formacion_profesional')
@login_required
@solo_egresado
def formacion_profesional():
    e = Egresado.query.get(current_user.id_egresado)
    logros = FormacionAcademica.query.filter_by(id_egresado=e.id_egresado)\
                                      .order_by(FormacionAcademica.fecha_obtencion).all()
    return render_template('egresado/formacion_profesional.html', e=e, logros=logros)


@egresado.route('/formacion_profesional/<int:id>/eliminar', methods=['POST'])
@login_required
@solo_egresado
def eliminar_logro(id):
    logro = FormacionAcademica.query.get_or_404(id)
    if logro.id_egresado != current_user.id_egresado:
        flash('No tienes permiso.', 'danger')
        return redirect(url_for('egresado.formacion_profesional'))
    db.session.delete(logro)
    db.session.commit()
    flash('Registro eliminado.', 'info')
    return redirect(url_for('egresado.formacion_profesional'))


@egresado.route('/formacion-profesional/nuevo', methods=['GET', 'POST'])
@login_required
@solo_egresado
def nuevo_grado_titulo():
    e = current_user.egresado
    nombre_programa = e.programa.nombre if hasattr(e, 'programa') and e.programa else ''

    if request.method == 'POST':
        tipo = request.form.get('tipo', '').strip()

        logro = FormacionAcademica(
            id_egresado     = e.id_egresado,
            tipo            = tipo,
            grado_titulo    = request.form.get('grado_titulo', '').strip(),
            institucion     = request.form.get('institucion', '').strip() or 'Universidad Nacional Daniel Alcides Carrión',
            fecha_obtencion = request.form.get('fecha_obtencion'),
            fuente          = 'SUNEDU',
        )
        db.session.add(logro)
        db.session.commit()

        flash('Grado/Título registrado correctamente. Puedes agregar el siguiente.', 'success')
        return redirect(url_for('egresado.nuevo_grado_titulo'))

    nombre_programa = e.programa.nombre if hasattr(e, 'programa') and e.programa else ''
    return render_template('egresado/nuevo_grado_titulo.html', e=e, nombre_programa=nombre_programa)


# ============================================
# CERTIFICADOS Y ESPECIALIZACIONES
# ============================================

@egresado.route('/certificados')
@login_required
@solo_egresado
def certificados():
    e = Egresado.query.get(current_user.id_egresado)
    lista = Certificado.query.filter_by(id_egresado=e.id_egresado)\
                             .order_by(Certificado.fecha_emision.desc()).all()
    externos = [c for c in lista if c.tipo == 'externo']
    internos = [c for c in lista if c.tipo == 'interno']
    return render_template('egresado/certificados.html', externos=externos, internos=internos)


@egresado.route('/certificados/nuevo', methods=['GET', 'POST'])
@login_required
@solo_egresado
def nuevo_certificado():
    if request.method == 'POST':
        cert = Certificado(
            id_egresado         = current_user.id_egresado,
            nombre              = request.form.get('nombre', '').strip(),
            institucion_emisora = request.form.get('institucion_emisora', '').strip(),
            tipo                = request.form.get('tipo', 'externo'),
            categoria           = request.form.get('categoria', 'curso'),
            nivel_idioma        = request.form.get('nivel_idioma') or None,
            fecha_emision       = request.form.get('fecha_emision') or None,
            url_credencial      = request.form.get('url_credencial', '').strip() or None,
        )
        db.session.add(cert)
        db.session.commit()
        flash('Certificado registrado correctamente. Puedes ingresar el siguiente.', 'success')
        return redirect(url_for('egresado.nuevo_certificado'))

    return render_template('egresado/nuevo_certificado.html')

@egresado.route('/certificados/<int:id>/eliminar', methods=['POST'])
@login_required
@solo_egresado
def eliminar_certificado(id):
    cert = Certificado.query.get_or_404(id)
    if cert.id_egresado != current_user.id_egresado:
        flash('No tienes permiso.', 'danger')
        return redirect(url_for('egresado.certificados'))
    db.session.delete(cert)
    db.session.commit()
    flash('Certificado eliminado.', 'info')
    return redirect(url_for('egresado.certificados'))


# ============================================
# HABILIDADES E INTERESES
# ============================================

@egresado.route('/habilidades/nueva', methods=['POST'])
@login_required
@solo_egresado
def nueva_habilidad():
    nombre = request.form.get('nombre', '').strip()
    tipo   = request.form.get('tipo', 'habilidad')

    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not nombre:
        if es_ajax:
            return jsonify({'ok': False, 'error': 'El nombre no puede estar vacío.'}), 400
        flash('El nombre no puede estar vacío.', 'warning')
        return redirect(url_for('egresado.editar_perfil'))

    h = Habilidad(id_egresado=current_user.id_egresado, nombre=nombre, tipo=tipo)
    db.session.add(h)
    db.session.commit()

    if es_ajax:
        return jsonify({'ok': True, 'id_habilidad': h.id_habilidad, 'nombre': h.nombre, 'tipo': h.tipo})

    flash('Agregado correctamente.', 'success')
    return redirect(url_for('egresado.editar_perfil'))


@egresado.route('/habilidades/<int:id>/eliminar', methods=['POST'])
@login_required
@solo_egresado
def eliminar_habilidad(id):
    h = Habilidad.query.get_or_404(id)
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if h.id_egresado != current_user.id_egresado:
        if es_ajax:
            return jsonify({'ok': False, 'error': 'No tienes permiso.'}), 403
        flash('No tienes permiso.', 'danger')
        return redirect(url_for('egresado.editar_perfil'))

    db.session.delete(h)
    db.session.commit()

    if es_ajax:
        return jsonify({'ok': True})

    flash('Eliminado.', 'info')
    return redirect(url_for('egresado.editar_perfil'))


# ============================================
# OFERTAS LABORALES
# ============================================

@egresado.route('/ofertas')
@login_required
@solo_egresado
def ofertas():
    return redirect(url_for('public.ofertas'))


# ==========================================
# GENERAR CV
# ==========================================

@egresado.route('/mi-cv')
@login_required
@solo_egresado
def seleccionar_cv():
    e              = Egresado.query.get(current_user.id_egresado)
    empleos_l      = Empleo.query.filter_by(id_egresado=e.id_egresado)\
                            .order_by(Empleo.fecha_inicio.desc()).all()
    logros_l       = FormacionAcademica.query.filter_by(id_egresado=e.id_egresado)\
                                            .order_by(FormacionAcademica.fecha_obtencion.desc()).all()
    certificados_l = Certificado.query.filter_by(id_egresado=e.id_egresado)\
                                     .order_by(Certificado.fecha_emision.desc()).all()
    return render_template('egresado/seleccionar_cv.html',
        e=e, empleos=empleos_l, logros=logros_l, certificados=certificados_l)


@egresado.route('/mi-cv/generar', methods=['POST'])
@login_required
@solo_egresado
def generar_cv_final():
    from app.utils.cv_pdf import generar_cv
    e = Egresado.query.get(current_user.id_egresado)

    if hasattr(e, 'titulo_cv'):
        e.titulo_cv = request.form.get('titulo_cv', '').strip() or None
    if hasattr(e, 'perfil_profesional'):
        e.perfil_profesional = request.form.get('perfil_profesional', '').strip() or None
    db.session.commit()

    ids_empleos      = request.form.getlist('empleos')
    ids_logros       = request.form.getlist('logros')
    ids_certificados = request.form.getlist('certificados')

    empleos_sel      = Empleo.query.filter(Empleo.id_empleo.in_(ids_empleos)).all() if ids_empleos else []
    logros_sel       = FormacionAcademica.query.filter(FormacionAcademica.id_formacion.in_(ids_logros)).all() if ids_logros else []
    certificados_sel = Certificado.query.filter(Certificado.id_certificado.in_(ids_certificados)).all() if ids_certificados else []

    habilidades_l = Habilidad.query.filter_by(id_egresado=e.id_egresado, tipo='habilidad').all()
    intereses_l   = Habilidad.query.filter_by(id_egresado=e.id_egresado, tipo='interes').all()
    idiomas_l     = Certificado.query.filter_by(id_egresado=e.id_egresado, categoria='idioma').all()

    pdf = generar_cv(e, empleos_sel, logros_sel, certificados_sel, habilidades_l, intereses_l, idiomas_l)
    nombre_archivo = f"CV_{e.apellido_paterno}_{e.nombres.split()[0]}.pdf"
    return send_file(pdf, mimetype='application/pdf', as_attachment=True, download_name=nombre_archivo)

# ==========================================
# ENCUESTAS
# ==========================================

FALTA = 'Responde todas las preguntas obligatorias.'


def _abierta(enc):
    """Publicada y dentro de su rango de fechas (el último día de fecha_fin aún cuenta)."""
    hoy = date.today()
    return (enc.estado == 'publicada'
            and (enc.fecha_inicio is None or enc.fecha_inicio <= hoy)
            and (enc.fecha_fin is None or enc.fecha_fin >= hoy))


def _leer_respuesta(p):
    """Lee del formulario la respuesta a una pregunta y la valida.
    Devuelve (Respuesta o None, error o None). None sin error = pregunta opcional sin responder."""
    campo = f'pregunta_{p.id_pregunta}'

    if p.tipo == 'texto':
        valor = request.form.get(campo, '').strip()
        if not valor:
            return None, (FALTA if p.obligatoria else None)
        return Respuesta(id_pregunta=p.id_pregunta, respuesta_texto=valor), None

    if p.tipo == 'numero':
        valor = request.form.get(campo, '').strip()
        if not valor:
            return None, (FALTA if p.obligatoria else None)
        try:
            numero = Decimal(valor)
        except InvalidOperation:
            return None, 'Ingresa un número válido.'
        if not numero.is_finite() or abs(numero) >= 10**8:      # la columna es DECIMAL(10,2)
            return None, 'Ingresa un número válido.'
        return Respuesta(id_pregunta=p.id_pregunta,
                         respuesta_numero=numero.quantize(Decimal('0.01'))), None

    if p.tipo == 'si_no':
        valor = request.form.get(campo)
        if valor not in ('si', 'no'):
            return None, (FALTA if p.obligatoria else None)
        return Respuesta(id_pregunta=p.id_pregunta, respuesta_si_no=1 if valor == 'si' else 0), None

    # opcion_unica / opcion_multiple: las opciones deben ser de esta pregunta
    validas = {o.id_opcion for o in p.opciones}
    try:
        elegidas = {int(v) for v in request.form.getlist(campo)}
    except ValueError:
        return None, 'Selección inválida.'
    if not elegidas:
        return None, (FALTA if p.obligatoria else None)
    if not elegidas <= validas or (p.tipo == 'opcion_unica' and len(elegidas) > 1):
        return None, 'Selección inválida.'
    return Respuesta(id_pregunta=p.id_pregunta,
                     opciones=[RespuestaOpcion(id_opcion=i) for i in sorted(elegidas)]), None


@egresado.route('/encuestas')
@login_required
@solo_egresado
def encuesta():
    hoy = date.today()
    respondidas_ids = {r[0] for r in db.session.query(EncuestaEnvio.id_encuesta)
                       .filter_by(id_egresado=current_user.id_egresado).all()}

    todas = (Encuesta.query.filter(Encuesta.estado != 'borrador')
             .order_by(Encuesta.anio.desc(), Encuesta.id_encuesta.desc()).all())

    disponibles, respondidas, pasadas = [], [], []
    for enc in todas:
        if _abierta(enc):
            (respondidas if enc.id_encuesta in respondidas_ids else disponibles).append(enc)
        elif enc.estado == 'cerrada' or (enc.fecha_fin and enc.fecha_fin < hoy):
            pasadas.append(enc)
        # una publicada que todavía no empieza no se muestra

    return render_template('egresado/encuesta.html', disponibles=disponibles,
                           respondidas=respondidas, pasadas=pasadas,
                           respondidas_ids=respondidas_ids)


@egresado.route('/encuestas/<int:id>', methods=['GET', 'POST'])
@login_required
@solo_egresado
def responder_encuesta(id):
    enc = db.get_or_404(Encuesta, id)
    id_egresado = current_user.id_egresado

    if not _abierta(enc):
        flash('Esta encuesta no está disponible.', 'warning')
        return redirect(url_for('egresado.encuesta'))
    if EncuestaEnvio.query.filter_by(id_encuesta=id, id_egresado=id_egresado).first():
        flash('Ya respondiste esta encuesta.', 'info')
        return redirect(url_for('egresado.encuesta'))

    preguntas = Pregunta.query.filter_by(id_encuesta=id).order_by(Pregunta.orden).all()

    if request.method == 'POST':
        respuestas, error = [], None
        for p in preguntas:
            resp, error = _leer_respuesta(p)
            if error:
                break
            if resp:
                respuestas.append(resp)
        if not error and not respuestas:
            error = 'Responde al menos una pregunta.'

        if error:
            flash(error, 'warning')
        else:
            db.session.add(EncuestaEnvio(id_encuesta=id, id_egresado=id_egresado,
                                         respuestas=respuestas))
            try:
                db.session.commit()
            except IntegrityError:        # doble clic o dos pestañas: la base lo impide (UNIQUE)
                db.session.rollback()
                flash('Ya respondiste esta encuesta.', 'info')
            else:
                flash('¡Gracias! Tus respuestas fueron enviadas.', 'success')
            return redirect(url_for('egresado.encuesta'))

    return render_template('egresado/responder_encuesta.html', encuesta=enc, preguntas=preguntas)