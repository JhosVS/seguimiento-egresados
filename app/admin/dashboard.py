# app/admin/dashboard.py
from collections import Counter

from flask import render_template, request, send_file
from flask_login import current_user
from sqlalchemy import and_, case, distinct, func, select

from app.admin import admin
from app.auth.decorators import requiere_rol
from app.extensions import db
from app.models import Curricula, Egresado, Empleo, EncuestaEnvio, FormacionAcademica, Sector

from app.admin.informes import generar_informe_pdf
from app.utils.historial import registrar
from app.utils.helpers import clave_empresa

GRADOS = [('bachiller', 'Bachiller', '#0d6efd'), ('titulado', 'Título profesional', '#198754'),
          ('maestria', 'Maestría', '#ffc107'), ('doctorado', 'Doctorado', '#dc3545')]
TOP_EMPRESAS = 10


def _pct(parte, total):
    return round(parte / total * 100, 1) if total else 0


def _empleo_actual(sectores=None):
    """Condición: el egresado tiene un empleo actual (opcionalmente en alguno de esos sectores)."""
    q = select(Empleo.id_empleo).where(
        Empleo.id_egresado == Egresado.id_egresado, Empleo.fecha_fin.is_(None))
    if sectores:
        q = q.where(Empleo.id_sector.in_(sectores))
    return q.exists()


def _filtros_de_url():
    a = request.args
    situacion = a.get('situacion', '')
    return {
        'anio_egreso': a.get('anio_egreso', type=int),
        'anio_ingreso': a.get('anio_ingreso', type=int),
        'situacion': situacion if situacion in ('con_empleo', 'sin_empleo') else '',
        'curricula': a.get('curricula', '').strip(),
        'sectores': a.getlist('sector', type=int),
    }

def _describir_filtros(f):
    partes = []
    if f['anio_egreso']:
        partes.append(f'año de egreso {f["anio_egreso"]}')
    if f['anio_ingreso']:
        partes.append(f'año de ingreso {f["anio_ingreso"]}')
    if f['curricula']:
        partes.append(f'currícula {f["curricula"]}')
    if f['situacion']:
        partes.append('con empleo actual' if f['situacion'] == 'con_empleo' else 'sin empleo actual')
    if f['sectores']:
        nombres = db.session.scalars(select(Sector.nombre).where(Sector.id_sector.in_(f['sectores']))
                                     .order_by(Sector.nombre)).all()
        partes.append('con empleo actual en el sector ' + ', '.join(nombres))
    return partes

def _egresados_filtrados(f):
    # El join con Curricula se mantiene siempre: evita que la subconsulta se confunda con la externa
    q = select(Egresado.id_egresado).join(Curricula, Egresado.id_curricula == Curricula.id_curricula)
    if f['anio_egreso']:
        q = q.where(Egresado.anio_egreso == f['anio_egreso'])
    if f['anio_ingreso']:
        q = q.where(Egresado.anio_ingreso == f['anio_ingreso'])
    if f['curricula']:
        q = q.where(Curricula.nombre == f['curricula'])
    if f['situacion'] == 'con_empleo':
        q = q.where(_empleo_actual())
    elif f['situacion'] == 'sin_empleo':
        q = q.where(~_empleo_actual())
    if f['sectores']:
        q = q.where(_empleo_actual(f['sectores']))
    return q


def _ranking_empresas(ids):
    """Top de empresas por cantidad de egresados distintos que trabajaron en ellas."""
    filas = db.session.execute(
        select(Empleo.id_egresado, Empleo.empresa_nombre).where(Empleo.id_egresado.in_(ids))).all()
    grupos = {}
    for id_egresado, nombre in filas:
        clave = clave_empresa(nombre)
        if clave:
            g = grupos.setdefault(clave, {'egresados': set(), 'nombres': Counter()})
            g['egresados'].add(id_egresado)
            g['nombres'][nombre.strip()] += 1
    ranking = [[g['nombres'].most_common(1)[0][0], len(g['egresados'])] for g in grupos.values()]
    ranking.sort(key=lambda r: (-r[1], r[0].lower()))
    return ranking[:TOP_EMPRESAS]


def _titulacion(ids, total):
    """Cuántos egresados tienen cada grado o título (una persona puede tener varios)."""
    conteo = dict(db.session.execute(
        select(FormacionAcademica.tipo, func.count(distinct(FormacionAcademica.id_egresado)))
        .where(FormacionAcademica.id_egresado.in_(ids))
        .group_by(FormacionAcademica.tipo)).all())
    return {'labels': [nombre for _, nombre, _ in GRADOS],
            'datos': [conteo.get(tipo, 0) for tipo, _, _ in GRADOS],
            'pct': [_pct(conteo.get(tipo, 0), total) for tipo, _, _ in GRADOS],
            'colores': [color for _, _, color in GRADOS]}


def obtener_tablero(f):
    """Todos los datos del tablero, con los filtros aplicados."""
    ids = _egresados_filtrados(f)
    en_ids = Egresado.id_egresado.in_(ids)

    por_genero = dict(db.session.execute(
        select(Egresado.genero, func.count()).where(en_ids).group_by(Egresado.genero)).all())
    total = sum(por_genero.values())
    varones, mujeres = por_genero.get('M', 0), por_genero.get('F', 0)

    con_empleo = db.session.scalar(select(func.count()).select_from(Egresado).where(en_ids, _empleo_actual()))
    con_algun_empleo = db.session.scalar(
        select(func.count(distinct(Empleo.id_egresado))).where(Empleo.id_egresado.in_(ids)))
    titulados = db.session.scalar(
        select(func.count(distinct(FormacionAcademica.id_egresado)))
        .where(FormacionAcademica.id_egresado.in_(ids), FormacionAcademica.tipo == 'titulado'))
    participaron = db.session.scalar(
        select(func.count(distinct(EncuestaEnvio.id_egresado))).where(EncuestaEnvio.id_egresado.in_(ids)))

    # Sector económico de los empleos actuales (si hay sectores marcados, solo esos)
    sector = func.coalesce(Sector.nombre, 'Sin sector')
    q_sector = (select(sector, func.count(Empleo.id_empleo))
                .select_from(Empleo).outerjoin(Sector, Empleo.id_sector == Sector.id_sector)
                .where(Empleo.id_egresado.in_(ids), Empleo.fecha_fin.is_(None)))
    if f['sectores']:
        q_sector = q_sector.where(Empleo.id_sector.in_(f['sectores']))
    sectores = [[s, c] for s, c in db.session.execute(
        q_sector.group_by(sector).order_by(func.count(Empleo.id_empleo).desc())).all()]

    # Por currícula
    actual = case((and_(Empleo.id_empleo.is_not(None), Empleo.fecha_fin.is_(None)), Egresado.id_egresado))
    bachiller = case((FormacionAcademica.tipo == 'bachiller', Egresado.id_egresado))
    titulado = case((FormacionAcademica.tipo == 'titulado', Egresado.id_egresado))
    postgrado = case((FormacionAcademica.tipo.in_(('maestria', 'doctorado')), Egresado.id_egresado))
    curriculas = db.session.execute(
        select(Curricula.nombre, func.count(distinct(actual)), func.count(distinct(Egresado.id_egresado)),
               func.count(distinct(bachiller)), func.count(distinct(titulado)), func.count(distinct(postgrado)))
        .select_from(Egresado)
        .join(Curricula, Egresado.id_curricula == Curricula.id_curricula)
        .outerjoin(Empleo, Empleo.id_egresado == Egresado.id_egresado)
        .outerjoin(FormacionAcademica, FormacionAcademica.id_egresado == Egresado.id_egresado)
        .where(en_ids).group_by(Curricula.nombre).order_by(Curricula.nombre)).all()

    return {
        'total': total, 'varones': varones, 'mujeres': mujeres, 'sin_genero': total - varones - mujeres,
        'con_empleo': con_empleo, 'pct_empleo': _pct(con_empleo, total),
        'titulados': titulados, 'pct_titulados': _pct(titulados, total),
        'participaron': participaron, 'pct_participacion': _pct(participaron, total),
        'situacion': [['Con empleo actual', con_empleo],
                      ['Solo empleos anteriores', max(0, con_algun_empleo - con_empleo)],
                      ['Sin empleo registrado', max(0, total - con_algun_empleo)]],
        'titulacion': _titulacion(ids, total), 'sectores': sectores,
        'empresas': _ranking_empresas(ids), 'curriculas': curriculas,
    }


def _opciones_tablero():
    """Valores de los desplegables de los filtros."""
    def distintos(columna):
        return [v for (v,) in db.session.execute(
            select(columna).where(columna.is_not(None)).distinct().order_by(columna.desc()))]
    return {
        'anios_egreso': distintos(Egresado.anio_egreso),
        'anios_ingreso': distintos(Egresado.anio_ingreso),
        'curriculas': [c for (c,) in db.session.execute(
            select(Curricula.nombre).join(Egresado, Egresado.id_curricula == Curricula.id_curricula)
            .distinct().order_by(Curricula.nombre))],
        'sectores': db.session.scalars(select(Sector).order_by(Sector.nombre)).all(),
    }


@admin.route('/admin')
@requiere_rol('administrador')
def dashboard():
    f = _filtros_de_url()
    datos = obtener_tablero(f)

    # HTMX pide solo los resultados; una carga normal (o volver atrás en el historial) trae la página completa
    if request.headers.get('HX-Request') and not request.headers.get('HX-History-Restore-Request'):
        return render_template('admin/_tablero.html', datos=datos)
    return render_template('admin/dashboard.html', datos=datos, f=f, **_opciones_tablero())

# Generar informe
@admin.route('/admin/informes/pdf')
@requiere_rol('administrador')
def informe_pdf():
    f = _filtros_de_url()
    filtros = _describir_filtros(f)
    pdf = generar_informe_pdf(obtener_tablero(f), filtros, current_user.personal.nombre_completo)
    registrar('consulta', 'informes',
              'Generó el informe PDF' + (f' ({"; ".join(filtros)})' if filtros else ''), guardar=True)
    return send_file(pdf, mimetype='application/pdf', as_attachment=True,
                     download_name='informe_egresados.pdf')