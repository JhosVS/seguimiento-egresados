# app/admin/informes.py
import io
from datetime import datetime

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

AZUL = colors.HexColor('#003876')
GRIS = colors.HexColor('#f1f5f9')
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre']

# Umbrales que usan las recomendaciones automáticas (ajústalos a criterio de la escuela)
MIN_COBERTURA = 50      # % mínimo de egresados con cuenta
MAX_SIN_EMPLEO = 30     # % máximo tolerable de cuentas sin ningún empleo registrado
MIN_TITULADOS = 50      # % mínimo de titulados


def _pct(parte, total):
    return round(parte / total * 100, 1) if total else 0


def _estilos():
    base = getSampleStyleSheet()
    texto = ParagraphStyle('texto', parent=base['Normal'], fontSize=9.5, leading=14,
                           alignment=TA_JUSTIFY, spaceAfter=6)
    return {
        'titulo': ParagraphStyle('titulo', parent=base['Title'], fontSize=18, textColor=AZUL,
                                 alignment=TA_CENTER, spaceAfter=4),
        'sub': ParagraphStyle('sub', parent=base['Normal'], fontSize=10, textColor=colors.grey,
                              alignment=TA_CENTER),
        'h1': ParagraphStyle('h1', parent=base['Heading2'], fontSize=12, textColor=AZUL,
                             spaceBefore=14, spaceAfter=6, keepWithNext=1),
        'texto': texto,
        'vineta': ParagraphStyle('vineta', parent=texto, leftIndent=14, bulletIndent=2),
        'nota': ParagraphStyle('nota', parent=base['Normal'], fontSize=8, leading=11,
                               textColor=colors.grey),
    }


def _tabla(filas, anchos, derecha=()):
    t = Table(filas, colWidths=anchos, repeatRows=1)
    estilo = [
        ('BACKGROUND', (0, 0), (-1, 0), AZUL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRIS]),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]
    estilo += [('ALIGN', (c, 0), (c, -1), 'RIGHT') for c in derecha]
    t.setStyle(TableStyle(estilo))
    return t


def _grafico_barras(etiquetas, valores, ancho):
    alto = 1.0 * cm + 0.75 * cm * len(etiquetas)
    dibujo = Drawing(ancho, alto)
    g = HorizontalBarChart()
    g.x, g.y, g.width, g.height = 5.5 * cm, 0.3 * cm, ancho - 7 * cm, alto - 0.6 * cm
    g.data = [list(reversed(valores))]                       # el primero queda arriba
    g.categoryAxis.categoryNames = list(reversed(etiquetas))
    g.categoryAxis.labels.fontSize = 8
    g.valueAxis.valueMin = 0
    g.valueAxis.valueMax = max(valores) * 1.2
    g.valueAxis.labels.fontSize = 8
    g.bars[0].fillColor = AZUL
    g.barLabelFormat = '%d'
    g.barLabels.fontSize = 8
    g.barLabels.nudge = 8
    dibujo.add(g)
    return dibujo


def _pie(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(2 * cm, 1.2 * cm, 'Sistema de Seguimiento de Egresados — UNDAC')
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f'Página {doc.page}')
    canvas.restoreState()


def _recomendaciones(d, sin_registro):
    """Observaciones automáticas a partir de los umbrales de arriba."""
    obs = []
    if d['total'] == 0:
        return ['Todavía no hay egresados registrados: el primer paso es cargar la base de egresados.']
    if d['pct_cuenta'] < MIN_COBERTURA:
        obs.append(f'La cobertura es de {d["pct_cuenta"]} %, por debajo del {MIN_COBERTURA} % deseable. '
                   'Conviene difundir el registro entre los egresados (correo, redes, eventos de la escuela).')
    if d['con_cuenta'] and _pct(sin_registro, d['con_cuenta']) > MAX_SIN_EMPLEO:
        obs.append(f'El {_pct(sin_registro, d["con_cuenta"])} % de los egresados con cuenta no registra ningún '
                   'empleo. Se recomienda recordarles completar su perfil laboral, aunque hoy no trabajen.')
    if d['pct_titulados'] < MIN_TITULADOS:
        obs.append(f'Solo el {d["pct_titulados"]} % tiene título registrado. Conviene verificar si falta '
                   'registrar el dato o si hay egresados por orientar en el proceso de titulación.')
    if not obs:
        obs.append('Los indicadores principales superan los umbrales definidos; se recomienda mantener '
                   'las campañas de actualización de datos.')
    return obs


def generar_informe_pdf(datos, generado_por, ambito=None):
    """Informe de seguimiento de egresados. `datos` es el diccionario de obtener_metricas()."""
    d = datos
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            title='Informe de seguimiento de egresados', author=generado_por)
    ancho = A4[0] - 4 * cm
    est = _estilos()
    ahora = datetime.now()
    fecha = f'{ahora.day} de {MESES[ahora.month - 1]} de {ahora.year}'

    total, con_cuenta = d['total'], d['con_cuenta']
    con_empleo, titulados = d['con_empleo'], d['titulados']
    sin_registro = dict(d['situacion']).get('Sin empleo registrado', 0)

    def parrafo(txt):
        return Paragraph(txt, est['texto'])

    # --- Encabezado ---
    ficha = Table([['Ámbito', ambito or 'Todos los egresados registrados'],
                   ['Fecha de emisión', fecha],
                   ['Generado por', generado_por]], colWidths=[3.5 * cm, ancho - 3.5 * cm])
    ficha.setStyle(TableStyle([('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                               ('FONTSIZE', (0, 0), (-1, -1), 9),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    story = [Paragraph('Informe de seguimiento de egresados', est['titulo']),
             Paragraph('Escuela de Sistemas y Computación — Universidad Nacional Daniel Alcides Carrión',
                       est['sub']),
             Spacer(1, 0.5 * cm), ficha, Spacer(1, 0.3 * cm),
             HRFlowable(width='100%', thickness=1, color=AZUL)]

    # --- 1. Resumen ejecutivo ---
    story += [Paragraph('1. Resumen ejecutivo', est['h1']), parrafo(
        f'Al {fecha}, la base del sistema registra <b>{total}</b> egresados. De ellos, <b>{con_cuenta}</b> '
        f'({d["pct_cuenta"]} %) tienen una cuenta y pueden mantener su perfil al día. Entre quienes tienen '
        f'cuenta, <b>{con_empleo}</b> ({d["pct_empleo"]} %) declaran un empleo actual, y <b>{titulados}</b> '
        f'egresados ({d["pct_titulados"]} % del total) registran su título profesional.')]

    # --- 2. Cobertura ---
    story += [Paragraph('2. Cobertura del seguimiento', est['h1']), _tabla(
        [['Indicador', 'Egresados', '% del total'],
         ['Egresados en la base', total, '100 %' if total else '0 %'],
         ['Con cuenta en el sistema', con_cuenta, f'{d["pct_cuenta"]} %'],
         ['Sin cuenta todavía', total - con_cuenta, f'{_pct(total - con_cuenta, total)} %']],
        [ancho - 7 * cm, 3.5 * cm, 3.5 * cm], derecha=(1, 2))]

    # --- 3. Situación laboral ---
    story += [Paragraph('3. Situación laboral', est['h1']), _tabla(
        [['Situación', 'Egresados', '% de los que tienen cuenta']] +
        [[n, c, f'{_pct(c, con_cuenta)} %'] for n, c in d['situacion']],
        [ancho - 8 * cm, 3 * cm, 5 * cm], derecha=(1, 2)), Spacer(1, 0.3 * cm)]
    if d['sector_data']:
        story.append(KeepTogether([
            parrafo('<b>Sector de los empleos actuales</b>'),
            _grafico_barras(d['sector_labels'], d['sector_data'], ancho)]))
    else:
        story.append(parrafo('Aún no hay empleos actuales registrados, por lo que no se puede mostrar '
                             'la distribución por sector.'))

    # --- 4. Formación académica ---
    story.append(Paragraph('4. Formación académica', est['h1']))
    if d['niveles']:
        story.append(_tabla([['Máximo nivel alcanzado', 'Egresados', '% del total']] +
                            [[n, c, f'{_pct(c, total)} %'] for n, c in d['niveles']],
                            [ancho - 7 * cm, 3.5 * cm, 3.5 * cm], derecha=(1, 2)))
    else:
        story.append(parrafo('Sin datos de formación registrados.'))

    # --- 5. Detalle por currícula ---
    story.append(Paragraph('5. Detalle por currícula', est['h1']))
    if d['curriculas']:
        story.append(_tabla(
            [['Currícula', 'Egresados', 'Con cuenta', '% cuenta', 'Con empleo', 'Titulados']] +
            [[n, e, c, f'{_pct(c, e)} %', emp, t] for n, e, c, emp, t in d['curriculas']],
            [ancho - 15 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm, 3 * cm], derecha=(1, 2, 3, 4, 5)))
    else:
        story.append(parrafo('Sin egresados registrados.'))

    # --- 6. Observaciones y recomendaciones ---
    story.append(Paragraph('6. Observaciones y recomendaciones', est['h1']))
    story += [Paragraph(o, est['vineta'], bulletText='•') for o in _recomendaciones(d, sin_registro)]

    # --- 7. Nota metodológica ---
    story += [Paragraph('7. Nota metodológica', est['h1']), Paragraph(
        'La información laboral y académica proviene de lo que cada egresado registra en el sistema, por '
        'lo que depende del nivel de participación. "Empleo actual" es el empleo registrado sin fecha de '
        'fin; "sin empleo registrado" indica que no cargó ninguno y no equivale a estar desempleado. '
        '"Titulado" cuenta a quienes registran el grado de título profesional. Los porcentajes de empleo '
        'se calculan sobre los egresados con cuenta; los de titulación y nivel, sobre el total de la base.',
        est['nota'])]

    doc.build(story, onFirstPage=_pie, onLaterPages=_pie)
    buf.seek(0)
    return buf