# app/admin/informes.py
from datetime import datetime
from io import BytesIO
from math import ceil

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZUL = colors.HexColor('#003876')
GRIS = colors.HexColor('#6c757d')
CLARO = colors.HexColor('#f1f3f5')
COLORES_NIVEL = ['#6c757d', '#0d6efd', '#198754', '#ffc107', '#dc3545']

_base = getSampleStyleSheet()
TITULO = ParagraphStyle('titulo', parent=_base['Title'], fontSize=18, textColor=AZUL, alignment=0, spaceAfter=2)
SUBTITULO = ParagraphStyle('sub', parent=_base['Normal'], fontSize=9, textColor=GRIS)
SECCION = ParagraphStyle('seccion', parent=_base['Heading3'], fontSize=11, textColor=AZUL, spaceBefore=12, spaceAfter=4)
TEXTO = ParagraphStyle('texto', parent=_base['Normal'], fontSize=9, leading=12)
NOTA = ParagraphStyle('nota', parent=_base['Normal'], fontSize=8, textColor=GRIS, leading=10)
KPI_VALOR = ParagraphStyle('kv', parent=_base['Normal'], fontSize=20, leading=24, alignment=1, textColor=AZUL)
KPI_TEXTO = ParagraphStyle('kt', parent=_base['Normal'], fontSize=8, leading=10, alignment=1, textColor=GRIS)


# ---------------------------------------------------------------- piezas reutilizables
def _kpis(items):
    """Fila de indicadores: items = [(valor, etiqueta), ...]."""
    celdas = [[Paragraph(f'<b>{v}</b>', KPI_VALOR), ] for v, _ in items]
    fila = [[[Paragraph(f'<b>{v}</b>', KPI_VALOR), Paragraph(e, KPI_TEXTO)] for v, e in items]]
    t = Table(fila, colWidths=[17 * cm / len(items)] * len(items))
    t.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                           ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                           ('BACKGROUND', (0, 0), (-1, -1), CLARO),
                           ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    return t


def _tabla(cabecera, filas, anchos, total=None):
    """Tabla simple: primera columna a la izquierda, el resto a la derecha."""
    datos = [cabecera] + [list(map(str, f)) for f in filas]
    if total:
        datos.append(list(map(str, total)))
    t = Table(datos, colWidths=anchos, repeatRows=1)
    estilo = [('BACKGROUND', (0, 0), (-1, 0), AZUL), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
              ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9),
              ('ALIGN', (1, 0), (-1, -1), 'RIGHT'), ('GRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
              ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CLARO]),
              ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]
    if total:
        estilo += [('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), ('BACKGROUND', (0, -1), (-1, -1), CLARO)]
    t.setStyle(TableStyle(estilo))
    return t


def _paso(maximo):
    return max(1, ceil(maximo / 5))


def _barras(etiquetas, valores, colores=None, horizontal=False, alto=190):
    """Gráfico de barras con el valor sobre cada barra."""
    d = Drawing(17 * cm, alto)
    g = HorizontalBarChart() if horizontal else VerticalBarChart()
    if horizontal:   # en horizontales la primera categoría queda abajo; se invierte para que el mayor quede arriba
        etiquetas, valores = etiquetas[::-1], valores[::-1]
        colores = colores[::-1] if colores else None
        g.x, g.width = 190, 250
    else:
        g.x, g.width = 40, 420
    g.y, g.height = 20, alto - 40
    g.data = [valores]
    g.categoryAxis.categoryNames = [e if len(e) <= 32 else e[:30] + '…' for e in etiquetas]
    g.categoryAxis.labels.fontSize = 8
    g.valueAxis.valueMin = 0
    g.valueAxis.valueMax = max(valores + [1]) * 1.15
    g.valueAxis.valueStep = _paso(max(valores + [1]))
    g.valueAxis.labels.fontSize = 8
    g.valueAxis.labelTextFormat = '%d'
    g.barLabelFormat = '%d'
    g.barLabels.fontSize = 8
    g.barLabels.nudge = 9 if horizontal else 7
    g.bars[0].fillColor = colors.HexColor('#0d6efd')
    for i, c in enumerate(colores or []):
        g.bars[(0, i)].fillColor = colors.HexColor(c)
    d.add(g)
    return d


def _pastel(valores, etiquetas):
    d = Drawing(17 * cm, 150)
    p = Pie()
    p.x, p.y, p.width, p.height = 200, 10, 130, 130
    p.data = valores
    p.labels = [f'{e}: {v}' for e, v in zip(etiquetas, valores)]
    p.slices.fontSize = 8
    for i, c in enumerate(['#198754', '#adb5bd']):
        p.slices[i].fillColor = colors.HexColor(c)
    d.add(p)
    return d


def _pie_de_pagina(c, doc):
    c.saveState()
    c.setFont('Helvetica', 8)
    c.setFillColor(GRIS)
    c.drawString(2 * cm, 1.2 * cm, 'Sistema de Seguimiento de Egresados')
    c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f'Página {doc.page}')
    c.restoreState()


def _encabezado(titulo, filtros, autor):
    return [Paragraph(titulo, TITULO),
            Paragraph(f'Generado el {datetime.now():%d/%m/%Y %H:%M} por {autor}', SUBTITULO),
            Spacer(1, 6),
            Paragraph('Filtros aplicados', SECCION),
            Paragraph(' · '.join(filtros) if filtros else 'Ninguno: se incluye a todos los egresados.', TEXTO)]


def _sin_datos():
    return [Spacer(1, 20), Paragraph('No hay egresados con estos filtros.', TEXTO)]


# ---------------------------------------------------------------- un informe por pestaña
def _informe_nivel(d):
    if d['total'] == 0:
        return _sin_datos()
    filas = [[n, c, f'{p}%'] for n, c, p in zip(d['labels'], d['datos'], d['pct'])]
    sin_genero = f' · Sin género registrado: {d["sin_genero"]}' if d['sin_genero'] else ''
    return [
        Spacer(1, 10),
        _kpis([(d['total'], 'Total de egresados'),
               (f'{d["varones"]} ({d["pct_varones"]}%)', 'Masculino'),
               (f'{d["mujeres"]} ({d["pct_mujeres"]}%)', 'Femenino')]),
        Paragraph('Egresados por nivel profesional', SECCION),
        _barras(d['labels'], d['datos'], COLORES_NIVEL),
        _tabla(['Nivel máximo alcanzado', 'Egresados', '% del total'], filas, [9 * cm, 4 * cm, 4 * cm],
               total=['Total', d['total'], '100%']),
        Spacer(1, 6),
        Paragraph('Cada persona se cuenta una sola vez, según su nivel máximo. '
                  '"Solo egresado" indica que no tiene grado ni título registrado.' + sin_genero, NOTA)]


def _informe_participacion(d):
    if not d['encuesta']:
        return [Spacer(1, 20), Paragraph('No hay encuestas publicadas todavía.', TEXTO)]
    if d['total'] == 0:
        return _sin_datos()
    filas = [[n, r, t, fa] for n, r, t, fa in d['filas']]
    return [
        Paragraph(f'Encuesta: {d["encuesta"].nombre} ({d["encuesta"].anio})', SECCION),
        _kpis([(f'{d["pct"]}%', 'Participación'),
               (d['respondieron'], 'Respondieron'),
               (d['faltan'], 'Pendientes')]),
        Spacer(1, 6),
        _pastel([d['respondieron'], d['faltan']], ['Respondieron', 'Pendientes']),
        Paragraph('Participación según nivel máximo', SECCION),
        _tabla(['Nivel', 'Respondieron', 'Total', 'Faltan'], filas, [7 * cm, 3.5 * cm, 3.5 * cm, 3 * cm],
               total=['Total', d['respondieron'], d['total'], d['faltan']])]


def _informe_empleabilidad(d, actual):
    if d['total'] == 0:
        return _sin_datos()
    cont = []
    cont += [Spacer(1, 10),
             _kpis([(d['total'], 'Egresados'),
                    (f'{d["con_empleo"]} ({d["pct_con"]}%)', 'Con empleo actual'),
                    (f'{d["sin_empleo"]} ({d["pct_sin"]}%)', 'Sin empleo actual')])]

    cont.append(Paragraph('Egresados por sector (empleo actual)' if actual else 'Egresados por sector (historial)', SECCION))
    if d['sectores']:
        cont.append(_tabla(['Sector', 'Egresados'], [[s, n] for _, s, n in d['sectores']], [13 * cm, 4 * cm]))
    else:
        cont.append(Paragraph('Sin empleos registrados con estos filtros.', TEXTO))

    cont.append(Paragraph('Top 10 empresas donde trabajan actualmente' if actual
                          else 'Top 10 empresas donde han trabajado', SECCION))
    if d['empresas']:
        nombres, valores = [e[0] for e in d['empresas']], [e[1] for e in d['empresas']]
        cont.append(_barras(nombres, valores, horizontal=True, alto=max(120, len(nombres) * 22 + 40)))
    else:
        cont.append(Paragraph('Sin datos con estos filtros.', TEXTO))

    cont += [Spacer(1, 6),
             Paragraph('"Sin empleo actual" no significa necesariamente desempleo: solo indica que no hay un empleo '
                       'actual registrado. ' +
                       ('Sector y empresas cuentan solo empleos actuales.' if actual else
                        'Sector y empresas cuentan todo el historial de empleos; un egresado puede figurar en '
                        'varios sectores o empresas.'), NOTA)]
    return cont


TITULOS = {'nivel': 'Informe de nivel profesional',
           'participacion': 'Informe de participación en encuestas',
           'empleabilidad': 'Informe de empleabilidad'}


def generar_informe(vista, datos, f, filtros, autor):
    """Devuelve el PDF (BytesIO) del informe de la pestaña indicada."""
    if vista == 'nivel':
        cuerpo = _informe_nivel(datos)
    elif vista == 'participacion':
        cuerpo = _informe_participacion(datos)
    else:
        cuerpo = _informe_empleabilidad(datos, f['actual'])

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=2 * cm, title=TITULOS[vista])
    doc.build(_encabezado(TITULOS[vista], filtros, autor) + cuerpo,
              onFirstPage=_pie_de_pagina, onLaterPages=_pie_de_pagina)
    buf.seek(0)
    return buf