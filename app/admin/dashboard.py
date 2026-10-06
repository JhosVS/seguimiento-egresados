# app/admin/dashboard.py
from datetime import date, timedelta

from flask import current_app, render_template, request, send_file
from flask_login import current_user
from sqlalchemy import and_, case, distinct, func, select

from app.admin import admin
from app.admin.informes import generar_informe_pdf
from app.extensions import db
from app.models import (Curricula, Egresado, Empleo, Facultad, FormacionAcademica, OfertaLaboral, ProgramaEstudio, Sector, Usuario)
from app.utils.helpers import alcance_personal

NIVELES = {0: 'Egresado (sin grado)', 1: 'Bachiller', 2: 'Titulado', 3: 'Maestría', 4: 'Doctorado'}


def _filtros_activos():
    return current_app.config.get('FILTRO_ESTRUCTURA_ACTIVO')


def _filtros_de_url():
    """Facultad/programa de la URL, solo si el filtro está activado."""
    if not _filtros_activos():
        return None, None
    return request.args.get('id_facultad', type=int), request.args.get('id_programa', type=int)


def _pct(parte, total):
    return round(parte / total * 100, 1) if total else 0


def _por_grupo(grupo, ids):
    """Por cada valor de `grupo` (año de egreso, currícula...):
    (grupo, egresados, con cuenta, con empleo actual, titulados)."""
    actual = case((and_(Empleo.id_empleo.is_not(None), Empleo.fecha_fin.is_(None)), Egresado.id_egresado))
    titulado = case((FormacionAcademica.tipo == 'titulado', Egresado.id_egresado))
    return db.session.execute(
        select(grupo,
               func.count(distinct(Egresado.id_egresado)),
               func.count(distinct(Usuario.id_usuario)),
               func.count(distinct(actual)),
               func.count(distinct(titulado)))
        .select_from(Egresado)
        .join(Curricula, Egresado.id_curricula == Curricula.id_curricula)
        .outerjoin(Usuario, Usuario.id_egresado == Egresado.id_egresado)
        .outerjoin(Empleo, Empleo.id_egresado == Egresado.id_egresado)
        .outerjoin(FormacionAcademica, FormacionAcademica.id_egresado == Egresado.id_egresado)
        .where(Egresado.id_egresado.in_(ids), grupo.is_not(None))
        .group_by(grupo).order_by(grupo)).all()


def obtener_metricas(personal, id_facultad=None, id_programa=None):
    """Datos del panel. El alcance del rol manda sobre los filtros de la URL."""
    fac_fijo, prog_fijo = alcance_personal(personal)
    if prog_fijo is not None:
        id_programa, id_facultad = prog_fijo, None
    elif fac_fijo is not None:
        id_facultad = fac_fijo

    ids = (select(Egresado.id_egresado)
           .join(Curricula, Egresado.id_curricula == Curricula.id_curricula)
           .join(ProgramaEstudio, Curricula.id_programa == ProgramaEstudio.id_programa))
    if id_facultad is not None:
        ids = ids.where(ProgramaEstudio.id_facultad == id_facultad)
    if id_programa is not None:
        ids = ids.where(ProgramaEstudio.id_programa == id_programa)
    en_alcance = Egresado.id_egresado.in_(ids)

    # --- Por currícula (de aquí salen también los totales) ---
    curriculas = _por_grupo(Curricula.nombre, ids)
    total = sum(c[1] for c in curriculas)
    con_cuenta = sum(c[2] for c in curriculas)
    con_empleo = sum(c[3] for c in curriculas)
    titulados = sum(c[4] for c in curriculas)

    # --- Situación laboral (solo egresados con cuenta) ---
    con_algun_empleo = db.session.scalar(
        select(func.count(distinct(Empleo.id_egresado))).where(Empleo.id_egresado.in_(ids)))
    situacion = [
        ('Con empleo actual', con_empleo),
        ('Solo empleos anteriores', max(0, con_algun_empleo - con_empleo)),
        ('Sin empleo registrado', max(0, con_cuenta - con_algun_empleo)),
    ]

    # --- Nivel académico máximo ---
    nivel = case((FormacionAcademica.tipo == 'doctorado', 4),
                 (FormacionAcademica.tipo == 'maestria', 3),
                 (FormacionAcademica.tipo == 'titulado', 2),
                 (FormacionAcademica.tipo == 'bachiller', 1))
    maximo = (select(func.max(nivel).label('n'))
              .where(FormacionAcademica.id_egresado.in_(ids))
              .group_by(FormacionAcademica.id_egresado)).subquery()
    conteo = dict(db.session.execute(select(maximo.c.n, func.count()).group_by(maximo.c.n)).all())
    conteo[0] = total - sum(conteo.values())
    niveles = [(NIVELES[k], conteo[k]) for k in sorted(NIVELES, reverse=True) if conteo.get(k)]

    # --- Sector económico (empleos actuales) ---
    sector = func.coalesce(Sector.nombre, 'Sin sector')
    sectores = db.session.execute(
        select(sector, func.count(Empleo.id_empleo))
        .select_from(Empleo).outerjoin(Sector, Empleo.id_sector == Sector.id_sector)
        .where(Empleo.id_egresado.in_(ids), Empleo.fecha_fin.is_(None))
        .group_by(sector).order_by(func.count(Empleo.id_empleo).desc()).limit(7)).all()

    # --- Listas para actuar ---
    hoy = date.today()
    por_vencer = db.session.scalars(
        select(OfertaLaboral)
        .where(OfertaLaboral.activa.is_(True),
               OfertaLaboral.fecha_vencimiento.between(hoy, hoy + timedelta(days=15)))
        .order_by(OfertaLaboral.fecha_vencimiento).limit(5)).all()

    sin_empleo = db.session.scalars(
        select(Egresado)
        .join(Usuario, Usuario.id_egresado == Egresado.id_egresado)
        .where(en_alcance,
               ~select(Empleo.id_empleo).where(Empleo.id_egresado == Egresado.id_egresado).exists())
        .order_by(Usuario.creado_en.desc()).limit(8)).all()

    return {
        'total': total, 'con_cuenta': con_cuenta, 'pct_cuenta': _pct(con_cuenta, total),
        'con_empleo': con_empleo, 'pct_empleo': _pct(con_empleo, con_cuenta),
        'titulados': titulados, 'pct_titulados': _pct(titulados, total),
        'situacion': situacion, 'niveles': niveles,
        'sector_labels': [s[0] for s in sectores], 'sector_data': [s[1] for s in sectores],
        'curriculas': curriculas, 'por_vencer': por_vencer, 'sin_empleo': sin_empleo,
    }


def _opciones_filtro(personal, id_facultad):
    """Listas de los desplegables facultad/programa (solo si el filtro está activo)."""
    fac_fijo, prog_fijo = alcance_personal(personal)
    q_fac = select(Facultad).where(Facultad.estado == 'activo').order_by(Facultad.nombre)
    q_prog = (select(ProgramaEstudio).where(ProgramaEstudio.estado == 'activo')
              .order_by(ProgramaEstudio.nombre))
    if prog_fijo is not None:               # rol de programa: sin filtros
        return [], db.session.scalars(q_prog.where(ProgramaEstudio.id_programa == prog_fijo)).all()
    if fac_fijo is not None:                # rol de facultad: solo la suya
        q_fac = q_fac.where(Facultad.id_facultad == fac_fijo)
        id_facultad = fac_fijo
    programas = (db.session.scalars(q_prog.where(ProgramaEstudio.id_facultad == id_facultad)).all()
                 if id_facultad is not None else [])
    return db.session.scalars(q_fac).all(), programas


@admin.route('/admin')
def dashboard():
    personal = current_user.personal
    id_facultad, id_programa = _filtros_de_url()

    facultades, programas = (_opciones_filtro(personal, id_facultad)
                             if _filtros_activos() else ([], []))

    return render_template('admin/dashboard.html',
                           facultades=facultades, programas=programas,
                           id_facultad=id_facultad, id_programa=id_programa,
                           **obtener_metricas(personal, id_facultad, id_programa))


@admin.route('/admin/informes/pdf')
def informe_pdf():
    personal = current_user.personal
    id_facultad, id_programa = _filtros_de_url()

    fac_fijo, prog_fijo = alcance_personal(personal)
    if prog_fijo is not None:
        id_programa, id_facultad = prog_fijo, None
    elif fac_fijo is not None:
        id_facultad = fac_fijo

    ambito = None   # el informe pone "Todos los egresados registrados"
    if id_programa is not None:
        p = db.session.get(ProgramaEstudio, id_programa)
        ambito = f'Programa: {p.nombre}' if p else None
    elif id_facultad is not None:
        f = db.session.get(Facultad, id_facultad)
        ambito = f'Facultad: {f.nombre}' if f else None

    datos = obtener_metricas(personal, id_facultad, id_programa)
    pdf = generar_informe_pdf(datos, personal.nombre_completo, ambito=ambito)
    return send_file(pdf, mimetype='application/pdf', as_attachment=True,
                     download_name='informe_egresados.pdf')