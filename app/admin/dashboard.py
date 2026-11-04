# app/admin/dashboard.py
from collections import Counter

from flask import abort, render_template, request, send_file
from flask_login import current_user
from sqlalchemy import case, distinct, func, select

from app.admin import admin
from app.admin.informes import generar_informe
from app.auth.decorators import requiere_rol
from app.extensions import db
from app.models import Curricula, Egresado, Empleo, Encuesta, EncuestaEnvio, FormacionAcademica, Sector
from app.utils.helpers import clave_empresa
from app.utils.historial import registrar

TOP_EMPRESAS = 10

# Nivel máximo de cada egresado (0 = solo egresado, sin grado ni título registrado)
NIVELES = {0: 'Solo egresado', 1: 'Bachiller', 2: 'Título profesional', 3: 'Maestría', 4: 'Doctorado'}
GRUPOS_PARTICIPACION = [('Solo egresados', (0,)), ('Bachilleres', (1,)),
                        ('Titulados', (2,)), ('Maestría / Doctorado', (3, 4))]


def _pct(parte, total):
    return round(parte / total * 100, 1) if total else 0


def _filtros():
    a = request.args
    return {'anio_egreso': a.get('anio_egreso', type=int),
            'curricula': a.get('curricula', '').strip(),
            'id_sector': a.get('id_sector', type=int),
            'id_encuesta': a.get('id_encuesta', type=int),
            'actual': a.get('actual') == '1'}


def _encuesta_por_defecto(f):
    """Si no se eligió encuesta, usa la más reciente que no sea borrador."""
    if not f['id_encuesta']:
        f['id_encuesta'] = db.session.scalar(
            select(Encuesta.id_encuesta).where(Encuesta.estado != 'borrador')
            .order_by(Encuesta.anio.desc(), Encuesta.id_encuesta.desc()).limit(1))


def _egresados(f):
    """Egresados que cumplen los filtros de perfil (año de egreso y currícula)."""
    # El join con Curricula se mantiene siempre: evita que la subconsulta se confunda con la externa
    q = select(Egresado.id_egresado).join(Curricula, Egresado.id_curricula == Curricula.id_curricula)
    if f['anio_egreso']:
        q = q.where(Egresado.anio_egreso == f['anio_egreso'])
    if f['curricula']:
        q = q.where(Curricula.nombre == f['curricula'])
    return q


def _nivel_por_egresado(ids):
    """{id_egresado: nivel máximo 0-4}. Los egresados sin formación quedan en 0."""
    rango = case((FormacionAcademica.tipo == 'doctorado', 4),
                 (FormacionAcademica.tipo == 'maestria', 3),
                 (FormacionAcademica.tipo == 'titulado', 2),
                 (FormacionAcademica.tipo == 'bachiller', 1), else_=0)
    return dict(db.session.execute(
        select(Egresado.id_egresado, func.max(rango))
        .outerjoin(FormacionAcademica, FormacionAcademica.id_egresado == Egresado.id_egresado)
        .where(Egresado.id_egresado.in_(ids))
        .group_by(Egresado.id_egresado)).all())


# ---------------------------------------------------------------- 1. Nivel profesional
def datos_nivel(f):
    ids = _egresados(f)
    niveles = _nivel_por_egresado(ids)
    total = len(niveles)
    cuenta = Counter(niveles.values())
    genero = dict(db.session.execute(
        select(Egresado.genero, func.count()).where(Egresado.id_egresado.in_(ids))
        .group_by(Egresado.genero)).all())
    varones, mujeres = genero.get('M', 0), genero.get('F', 0)
    orden = [0, 1, 2, 3, 4]
    return {'total': total,
            'varones': varones, 'mujeres': mujeres, 'sin_genero': total - varones - mujeres,
            'pct_varones': _pct(varones, total), 'pct_mujeres': _pct(mujeres, total),
            'labels': [NIVELES[n] for n in orden],
            'datos': [cuenta[n] for n in orden],
            'pct': [_pct(cuenta[n], total) for n in orden]}


# ---------------------------------------------------------------- 2. Participación en encuestas
def datos_participacion(f):
    encuesta = db.session.get(Encuesta, f['id_encuesta']) if f['id_encuesta'] else None
    if encuesta is None:
        return {'encuesta': None}
    niveles = _nivel_por_egresado(_egresados(f))
    respondieron = set(db.session.scalars(
        select(EncuestaEnvio.id_egresado).where(
            EncuestaEnvio.id_encuesta == encuesta.id_encuesta,
            EncuestaEnvio.id_egresado.in_(list(niveles))))) if niveles else set()

    filas = []   # [grupo, respondieron, total del grupo, faltan]
    for nombre, rangos in GRUPOS_PARTICIPACION:
        grupo = [i for i, r in niveles.items() if r in rangos]
        resp = sum(1 for i in grupo if i in respondieron)
        filas.append([nombre, resp, len(grupo), len(grupo) - resp])

    total, resp = len(niveles), len(respondieron)
    return {'encuesta': encuesta, 'total': total, 'respondieron': resp,
            'faltan': total - resp, 'pct': _pct(resp, total), 'filas': filas}


# ---------------------------------------------------------------- 3. Empleabilidad
def _ranking_empresas(ids, id_sector, solo_actual):
    """Top de empresas por egresados distintos. solo_actual = [] (historial) o [fecha_fin es nula]."""
    q = select(Empleo.id_egresado, Empleo.empresa_nombre).where(Empleo.id_egresado.in_(ids), *solo_actual)
    if id_sector:
        q = q.where(Empleo.id_sector == id_sector)
    grupos = {}
    for id_egresado, nombre in db.session.execute(q).all():
        clave = clave_empresa(nombre)
        if clave:
            g = grupos.setdefault(clave, {'egresados': set(), 'nombres': Counter()})
            g['egresados'].add(id_egresado)
            g['nombres'][nombre.strip()] += 1
    ranking = [[g['nombres'].most_common(1)[0][0], len(g['egresados'])] for g in grupos.values()]
    ranking.sort(key=lambda r: (-r[1], r[0].lower()))
    return ranking[:TOP_EMPRESAS]


def datos_empleabilidad(f):
    ids = _egresados(f)
    total = db.session.scalar(select(func.count()).select_from(Egresado).where(Egresado.id_egresado.in_(ids)))
    con_empleo = db.session.scalar(
        select(func.count(distinct(Empleo.id_egresado)))
        .where(Empleo.id_egresado.in_(ids), Empleo.fecha_fin.is_(None)))

    # El interruptor "solo empleo actual" afecta a la tabla de sectores y al top de empresas
    solo_actual = [Empleo.fecha_fin.is_(None)] if f['actual'] else []

    nombre_sector = func.coalesce(Sector.nombre, 'Sin sector')
    sectores = db.session.execute(
        select(Sector.id_sector, nombre_sector, func.count(distinct(Empleo.id_egresado)))
        .select_from(Empleo).outerjoin(Sector, Empleo.id_sector == Sector.id_sector)
        .where(Empleo.id_egresado.in_(ids), *solo_actual)
        .group_by(Sector.id_sector, nombre_sector)
        .order_by(func.count(distinct(Empleo.id_egresado)).desc())).all()

    return {'total': total, 'con_empleo': con_empleo, 'sin_empleo': total - con_empleo,
            'pct_con': _pct(con_empleo, total), 'pct_sin': _pct(total - con_empleo, total),
            'sectores': sectores, 'empresas': _ranking_empresas(ids, f['id_sector'], solo_actual)}


# ---------------------------------------------------------------- Rutas
def _opciones():
    """Valores de los desplegables."""
    return {
        'anios_egreso': [v for (v,) in db.session.execute(
            select(Egresado.anio_egreso).where(Egresado.anio_egreso.is_not(None))
            .distinct().order_by(Egresado.anio_egreso.desc()))],
        'curriculas': db.session.scalars(select(Curricula).order_by(Curricula.nombre)).all(),
        'sectores': db.session.scalars(select(Sector).order_by(Sector.nombre)).all(),
        'encuestas': db.session.scalars(
            select(Encuesta).where(Encuesta.estado != 'borrador')
            .order_by(Encuesta.anio.desc(), Encuesta.id_encuesta.desc())).all(),
    }


def _responder(vista, datos, f):
    # HTMX pide solo los resultados; carga normal (o volver atrás) trae la página completa
    if request.headers.get('HX-Request') and not request.headers.get('HX-History-Restore-Request'):
        return render_template(f'admin/_tablero_{vista}.html', datos=datos, f=f)
    return render_template('admin/dashboard.html', vista=vista, datos=datos, f=f, **_opciones())


@admin.route('/admin')
@requiere_rol('administrador')
def dashboard():
    f = _filtros()
    return _responder('nivel', datos_nivel(f), f)


@admin.route('/admin/participacion')
@requiere_rol('administrador')
def participacion():
    f = _filtros()
    _encuesta_por_defecto(f)
    return _responder('participacion', datos_participacion(f), f)


@admin.route('/admin/empleabilidad')
@requiere_rol('administrador')
def empleabilidad():
    f = _filtros()
    return _responder('empleabilidad', datos_empleabilidad(f), f)


CALCULOS = {'nivel': datos_nivel, 'participacion': datos_participacion, 'empleabilidad': datos_empleabilidad}


def _describir_filtros(vista, f):
    """Los filtros que se ven en la pestaña, en texto, para el encabezado del PDF."""
    partes = []
    if f['anio_egreso']:
        partes.append(f'Año de egreso: {f["anio_egreso"]}')
    if f['curricula']:
        partes.append(f'Currícula: {f["curricula"]}')
    if vista == 'empleabilidad':
        if f['id_sector']:
            sector = db.session.get(Sector, f['id_sector'])
            partes.append(f'Sector (empresas): {sector.nombre if sector else f["id_sector"]}')
        if f['actual']:
            partes.append('Solo empleo actual')
    if vista == 'participacion' and f['id_encuesta']:
        encuesta = db.session.get(Encuesta, f['id_encuesta'])
        if encuesta:
            partes.append(f'Encuesta: {encuesta.nombre} ({encuesta.anio})')
    return partes


@admin.route('/admin/informe/<vista>')
@requiere_rol('administrador')
def informe(vista):
    if vista not in CALCULOS:
        abort(404)
    f = _filtros()
    if vista == 'participacion':
        _encuesta_por_defecto(f)
    filtros = _describir_filtros(vista, f)
    pdf = generar_informe(vista, CALCULOS[vista](f), f, filtros, current_user.personal.nombre_completo)
    registrar('consulta', 'informes',
              f'Generó el informe de {vista}' + (f' ({"; ".join(filtros)})' if filtros else ''), guardar=True)
    return send_file(pdf, mimetype='application/pdf', as_attachment=True,
                     download_name=f'informe_{vista}.pdf')