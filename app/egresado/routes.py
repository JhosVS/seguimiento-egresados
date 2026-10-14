# app/egresado/routes.py
import os
import uuid
from flask import send_from_directory, current_app, abort
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
from datetime import datetime

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
# EXPERIENCIA LABORAL (antes "Empleos")
# Todo ocurre en una sola página: la tabla se registra y edita en el sitio.
# ============================================
TIPOS_CONTRATO = ['Nombrado', 'Contratado', 'Practicante', 'Independiente']


def _fecha(valor):
    """'2026-10-14' -> date. Si viene vacío o mal escrito -> None."""
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date() if valor else None
    except ValueError:
        return None


def _contexto_empleos(nuevo=False, editando=None, datos=None, errores=None):
    """Todo lo que necesita la tabla para dibujarse."""
    lista = (Empleo.query.filter_by(id_egresado=current_user.id_egresado)
             .order_by(Empleo.fecha_fin.is_(None).desc(), Empleo.fecha_inicio.desc())
             .all())
    return dict(
        empleos=lista,
        sectores=Sector.query.order_by(Sector.nombre).all(),
        tipos_contrato=TIPOS_CONTRATO,
        nuevo=nuevo,             # True = mostrar la fila para registrar uno nuevo
        editando=editando,       # id del empleo que se está editando
        datos=datos or {},       # lo que el usuario escribió (para no perderlo si hay un error)
        errores=errores or [],
    )


def _tabla_empleos(**kwargs):
    return render_template('egresado/_tabla_empleos.html', **_contexto_empleos(**kwargs))


def _validar_empleo(form, empleo=None):
    """Devuelve (errores, valores_limpios)."""
    errores = []
    empresa = form.get('empresa_nombre', '').strip()
    cargo = form.get('cargo', '').strip()
    contrato = form.get('tipo_contrato', '').strip()
    es_actual = form.get('es_actual') == 'on'
    f_inicio = _fecha(form.get('fecha_inicio'))
    f_fin = None if es_actual else _fecha(form.get('fecha_fin'))

    try:
        id_sector = int(form.get('id_sector')) if form.get('id_sector') else None
    except ValueError:
        id_sector = None
        errores.append('El sector no es válido.')
    if id_sector and not db.session.get(Sector, id_sector):
        errores.append('El sector no existe.')

    if not empresa:
        errores.append('Escribe la empresa o institución.')
    if not cargo:
        errores.append('Escribe el cargo.')
    if not f_inicio:
        errores.append('La fecha de inicio es obligatoria (día, mes y año).')
    if not es_actual and not f_fin:
        errores.append('Indica la fecha de fin o marca "Actual".')
    if f_inicio and f_fin and f_fin < f_inicio:
        errores.append('La fecha de fin no puede ser anterior a la de inicio.')
    # Se acepta un valor antiguo (de cuando el campo era libre) solo si ya lo tenía el empleo
    if contrato and contrato not in TIPOS_CONTRATO and not (empleo and contrato == empleo.tipo_contrato):
        errores.append('El tipo de contrato no es válido.')

    valores = dict(
        empresa_nombre=empresa[:200],
        id_sector=id_sector,
        cargo=cargo[:150],
        tipo_contrato=contrato or None,
        fecha_inicio=f_inicio,
        fecha_fin=f_fin,
        funciones=form.get('funciones', '').strip() or None,
    )
    return errores, valores


def _guardar_empleo(empleo=None):
    errores, valores = _validar_empleo(request.form, empleo)
    if errores:
        # Se vuelve a mostrar la fila con lo que escribió y los errores
        return _tabla_empleos(nuevo=empleo is None,
                              editando=empleo.id_empleo if empleo else None,
                              datos=request.form.to_dict(), errores=errores)

    if empleo is None:
        empleo = Empleo(id_egresado=current_user.id_egresado)
        db.session.add(empleo)
    for campo, valor in valores.items():
        setattr(empleo, campo, valor)
    db.session.commit()
    return _tabla_empleos()


@egresado.route('/empleos')
@login_required
@solo_egresado
def empleos():
    return render_template('egresado/empleos.html', **_contexto_empleos())


@egresado.route('/empleos/tabla')
@login_required
@solo_egresado
def empleos_tabla():
    """Solo la tabla. ?nuevo=1 abre la fila de registro; ?editar=<id> abre la de edición."""
    return _tabla_empleos(nuevo=request.args.get('nuevo') == '1',
                          editando=request.args.get('editar', type=int))


@egresado.route('/empleos/guardar', methods=['POST'])
@login_required
@solo_egresado
def guardar_empleo_nuevo():
    return _guardar_empleo()


@egresado.route('/empleos/<int:id>/guardar', methods=['POST'])
@login_required
@solo_egresado
def guardar_empleo(id):
    empleo = Empleo.query.filter_by(id_empleo=id, id_egresado=current_user.id_egresado).first_or_404()
    return _guardar_empleo(empleo)


@egresado.route('/empleos/<int:id>/eliminar', methods=['POST'])
@login_required
@solo_egresado
def eliminar_empleo(id):
    empleo = Empleo.query.filter_by(id_empleo=id, id_egresado=current_user.id_egresado).first_or_404()
    db.session.delete(empleo)
    db.session.commit()
    return _tabla_empleos()


# ============================================
# FORMACIÓN PROFESIONAL (grados y títulos)
# Se registra y edita en la misma tabla.
# ============================================
TIPOS_GRADO = [('bachiller', 'Bachiller'), ('titulado', 'Título profesional'),
               ('maestria', 'Maestría'), ('doctorado', 'Doctorado')]
INSTITUCION_UNDAC = 'Universidad Nacional Daniel Alcides Carrión'


def _contexto_formacion(nuevo=False, editando=None, datos=None, errores=None):
    e = db.session.get(Egresado, current_user.id_egresado)
    logros = (FormacionAcademica.query.filter_by(id_egresado=e.id_egresado)
              .order_by(FormacionAcademica.fecha_obtencion).all())
    return dict(
        e=e,
        logros=logros,
        tipos=TIPOS_GRADO,
        etiqueta_tipo=dict(TIPOS_GRADO),
        institucion_defecto=INSTITUCION_UNDAC,
        hoy=datetime.now().date().isoformat(),
        nuevo=nuevo,
        editando=editando,
        datos=datos or {},
        errores=errores or [],
    )


def _tabla_formacion(**kwargs):
    return render_template('egresado/_tabla_formacion.html', **_contexto_formacion(**kwargs))


def _validar_grado(form):
    errores = []
    tipo = form.get('tipo', '').strip()
    grado = form.get('grado_titulo', '').strip()
    institucion = form.get('institucion', '').strip()
    fecha = _fecha(form.get('fecha_obtencion'))

    if tipo not in dict(TIPOS_GRADO):
        errores.append('Selecciona el tipo (bachiller, título, maestría o doctorado).')
    if not grado:
        errores.append('Escribe el grado o título.')
    if not institucion:
        errores.append('Escribe la institución.')
    if not fecha:
        errores.append('La fecha del diploma es obligatoria y debe ser válida.')
    elif fecha > datetime.now().date():
        errores.append('La fecha del diploma no puede ser futura.')

    valores = dict(tipo=tipo, grado_titulo=grado[:300], institucion=institucion[:200],
                   fecha_obtencion=fecha)
    return errores, valores


def _guardar_grado(logro=None):
    errores, valores = _validar_grado(request.form)
    if errores:
        return _tabla_formacion(nuevo=logro is None,
                                editando=logro.id_formacion if logro else None,
                                datos=request.form.to_dict(), errores=errores)

    if logro is None:
        logro = FormacionAcademica(id_egresado=current_user.id_egresado, fuente='SUNEDU')
        db.session.add(logro)
    for campo, valor in valores.items():
        setattr(logro, campo, valor)
    db.session.commit()
    return _tabla_formacion()


@egresado.route('/formacion_profesional')
@login_required
@solo_egresado
def formacion_profesional():
    contexto = _contexto_formacion()
    return render_template('egresado/formacion_profesional.html',
                           nombre_programa=contexto['e'].programa.nombre, **contexto)


@egresado.route('/formacion_profesional/tabla')
@login_required
@solo_egresado
def formacion_profesional_tabla():
    return _tabla_formacion(nuevo=request.args.get('nuevo') == '1',
                            editando=request.args.get('editar', type=int))


@egresado.route('/formacion_profesional/guardar', methods=['POST'])
@login_required
@solo_egresado
def guardar_grado_nuevo():
    return _guardar_grado()


@egresado.route('/formacion_profesional/<int:id>/guardar', methods=['POST'])
@login_required
@solo_egresado
def guardar_grado(id):
    logro = FormacionAcademica.query.filter_by(id_formacion=id,
                                               id_egresado=current_user.id_egresado).first_or_404()
    return _guardar_grado(logro)


@egresado.route('/formacion_profesional/<int:id>/eliminar', methods=['POST'])
@login_required
@solo_egresado
def eliminar_logro(id):
    logro = FormacionAcademica.query.filter_by(id_formacion=id,
                                               id_egresado=current_user.id_egresado).first_or_404()
    db.session.delete(logro)
    db.session.commit()
    return _tabla_formacion()


# ============================================
# FORMACIÓN COMPLEMENTARIA (antes "Certificados")
# Se registra y edita en la misma tabla, con PDF opcional.
# ============================================
CATEGORIAS_CERT = [('curso', 'Curso'), ('capacitacion', 'Capacitación'), ('taller', 'Taller'),
                   ('idioma', 'Idioma'), ('otro', 'Otro')]
NIVELES_IDIOMA = [('basico', 'Básico'), ('intermedio', 'Intermedio'), ('avanzado', 'Avanzado')]
MAX_PDF_BYTES = 5 * 1024 * 1024     # 5 MB


# --- PDF: carpeta PRIVADA (instance/), no pública. Se sirve solo con permiso ---
def _carpeta_certificados():
    carpeta = os.path.join(current_app.instance_path, 'certificados')
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def _revisar_pdf(archivo):
    """Devuelve un mensaje de error, o None si el PDF es válido."""
    if not archivo.filename.lower().endswith('.pdf'):
        return 'El archivo debe ser un PDF.'
    cabecera = archivo.stream.read(5)
    archivo.stream.seek(0, os.SEEK_END)
    tamano = archivo.stream.tell()
    archivo.stream.seek(0)
    if cabecera != b'%PDF-':          # se revisa el contenido real, no solo la extensión
        return 'El archivo no es un PDF válido.'
    if tamano > MAX_PDF_BYTES:
        return 'El PDF no puede pesar más de 5 MB.'
    return None


def _guardar_pdf(archivo):
    nombre = f'{uuid.uuid4().hex}.pdf'      # nombre aleatorio: no se usa el del usuario
    archivo.save(os.path.join(_carpeta_certificados(), nombre))
    return nombre


def _borrar_pdf(nombre):
    if not nombre:
        return
    ruta = os.path.join(_carpeta_certificados(), os.path.basename(nombre))
    if os.path.isfile(ruta):
        os.remove(ruta)


# --- Tabla ---
def _contexto_certificados(nuevo=False, editando=None, datos=None, errores=None):
    lista = (Certificado.query.filter_by(id_egresado=current_user.id_egresado)
             .order_by(Certificado.fecha_emision.is_(None), Certificado.fecha_emision.desc())
             .all())
    return dict(
        certificados=lista,
        categorias=CATEGORIAS_CERT,
        niveles=NIVELES_IDIOMA,
        etiqueta_cat=dict(CATEGORIAS_CERT),
        etiqueta_nivel=dict(NIVELES_IDIOMA),
        nuevo=nuevo,
        editando=editando,
        datos=datos or {},
        errores=errores or [],
    )


def _tabla_certificados(**kwargs):
    return render_template('egresado/_tabla_certificados.html', **_contexto_certificados(**kwargs))


def _validar_certificado(form, archivo):
    errores = []
    nombre = form.get('nombre', '').strip()
    institucion = form.get('institucion_emisora', '').strip()
    categoria = form.get('categoria', '')
    nivel = form.get('nivel_idioma') or None
    url = form.get('url_credencial', '').strip() or None
    fecha_texto = form.get('fecha_emision', '')
    fecha = _fecha(fecha_texto)

    if not nombre:
        errores.append('Escribe el nombre del certificado.')
    if not institucion:
        errores.append('Escribe la institución emisora.')
    if categoria not in dict(CATEGORIAS_CERT):
        errores.append('La categoría no es válida.')
    if categoria == 'idioma':
        if nivel and nivel not in dict(NIVELES_IDIOMA):
            errores.append('El nivel de idioma no es válido.')
    else:
        nivel = None        # la base solo permite nivel si la categoría es idioma
    if fecha_texto and not fecha:
        errores.append('La fecha no es válida.')
    if url and not url.lower().startswith(('http://', 'https://')):
        errores.append('La URL debe empezar con http:// o https://')
    if archivo and archivo.filename:
        error_pdf = _revisar_pdf(archivo)
        if error_pdf:
            errores.append(error_pdf)

    valores = dict(
        nombre=nombre[:255],
        institucion_emisora=institucion[:200],
        categoria=categoria,
        nivel_idioma=nivel,
        fecha_emision=fecha,
        url_credencial=url,
    )
    return errores, valores


def _guardar_certificado(cert=None):
    archivo = request.files.get('archivo')
    errores, valores = _validar_certificado(request.form, archivo)
    if errores:
        return _tabla_certificados(nuevo=cert is None,
                                   editando=cert.id_certificado if cert else None,
                                   datos=request.form.to_dict(), errores=errores)

    if cert is None:
        cert = Certificado(id_egresado=current_user.id_egresado)
        db.session.add(cert)
    for campo, valor in valores.items():
        setattr(cert, campo, valor)

    pdf_anterior = cert.ruta_archivo
    if archivo and archivo.filename:
        cert.ruta_archivo = _guardar_pdf(archivo)       # PDF nuevo (reemplaza al anterior)
    elif request.form.get('quitar_pdf') == 'on':
        cert.ruta_archivo = None
    db.session.commit()

    if pdf_anterior and pdf_anterior != cert.ruta_archivo:
        _borrar_pdf(pdf_anterior)
    return _tabla_certificados()


@egresado.route('/certificados')
@login_required
@solo_egresado
def certificados():
    return render_template('egresado/certificados.html', **_contexto_certificados())


@egresado.route('/certificados/tabla')
@login_required
@solo_egresado
def certificados_tabla():
    return _tabla_certificados(nuevo=request.args.get('nuevo') == '1',
                               editando=request.args.get('editar', type=int))


@egresado.route('/certificados/guardar', methods=['POST'])
@login_required
@solo_egresado
def guardar_certificado_nuevo():
    return _guardar_certificado()


@egresado.route('/certificados/<int:id>/guardar', methods=['POST'])
@login_required
@solo_egresado
def guardar_certificado(id):
    cert = Certificado.query.filter_by(id_certificado=id,
                                       id_egresado=current_user.id_egresado).first_or_404()
    return _guardar_certificado(cert)


@egresado.route('/certificados/<int:id>/eliminar', methods=['POST'])
@login_required
@solo_egresado
def eliminar_certificado(id):
    cert = Certificado.query.filter_by(id_certificado=id,
                                       id_egresado=current_user.id_egresado).first_or_404()
    pdf = cert.ruta_archivo
    db.session.delete(cert)
    db.session.commit()
    _borrar_pdf(pdf)
    return _tabla_certificados()


@egresado.route('/certificados/<int:id>/archivo')
@login_required
def archivo_certificado(id):
    """Entrega el PDF solo a su dueño o al personal."""
    cert = db.session.get(Certificado, id)
    if cert is None or not cert.ruta_archivo:
        abort(404)
    if not (current_user.es_personal or cert.id_egresado == current_user.id_egresado):
        abort(403)
    return send_from_directory(_carpeta_certificados(), os.path.basename(cert.ruta_archivo),
                               mimetype='application/pdf',
                               download_name=f'certificado-{cert.id_certificado}.pdf')


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