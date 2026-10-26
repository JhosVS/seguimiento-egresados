# app/admin/informes.py
import io
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZUL = colors.HexColor('#003876')
GRIS = colors.HexColor('#f1f5f9')
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre']

# Umbrales de las recomendaciones automáticas (ajústalos a criterio de la Escuela)
MAX_SIN_EMPLEO = 30        # % máximo tolerable de egresados sin ningún empleo registrado
MIN_TITULADOS = 50         # % mínimo de titulados
MIN_PARTICIPACION = 50     # % mínimo que respondió alguna encuesta
MUESTRA_MINIMA = 30        # con menos egresados, los porcentajes se interpretan con cautela


def _estilo(nombre, **kw):
    base = dict(fontName='Times-Roman', fontSize=12, leading=18)   # Times 12, interlineado 1.5 (12 × 1.5)
    base.update(kw)
    return ParagraphStyle(nombre, **base)


E = {
    'titulo': _estilo('titulo', fontName='Times-Bold', fontSize=16, leading=22, alignment=TA_CENTER,
                      textColor=AZUL, spaceAfter=2),
    'sub': _estilo('sub', fontSize=11, leading=15, alignment=TA_CENTER, textColor=colors.grey),
    'h1': _estilo('h1', fontName='Times-Bold', textColor=AZUL, spaceBefore=12, spaceAfter=4, keepWithNext=1),
    'texto': _estilo('texto', alignment=TA_JUSTIFY, spaceAfter=6),
    'vineta': _estilo('vineta', alignment=TA_JUSTIFY, leftIndent=18, bulletIndent=4, spaceAfter=4),
    'nota': _estilo('nota', fontSize=10, leading=15, alignment=TA_JUSTIFY, textColor=colors.HexColor('#444444')),
    'celda': _estilo('celda', fontSize=10, leading=13),
    'celda_d': _estilo('celda_d', fontSize=10, leading=13, alignment=TA_RIGHT),
    'cab': _estilo('cab', fontName='Times-Bold', fontSize=10, leading=13, textColor=colors.white),
    'cab_d': _estilo('cab_d', fontName='Times-Bold', fontSize=10, leading=13, textColor=colors.white,
                     alignment=TA_RIGHT),
}


def _pct(parte, total):
    return round(parte / total * 100, 1) if total else 0


def _egr(n):
    return f'{n} egresado' if n == 1 else f'{n} egresados'


def _p(texto):
    return Paragraph(texto, E['texto'])


def _tabla(cabecera, filas, anchos, derecha=()):
    datos = [[Paragraph(c, E['cab_d' if i in derecha else 'cab']) for i, c in enumerate(cabecera)]]
    for fila in filas:
        datos.append([Paragraph(escape(str(v)), E['celda_d' if i in derecha else 'celda'])
                      for i, v in enumerate(fila)])
    t = Table(datos, colWidths=anchos, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), AZUL),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRIS]),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def _pie(canvas, doc):
    canvas.saveState()
    canvas.setFont('Times-Roman', 9)
    canvas.setFillColor(colors.grey)
    canvas.drawString(2.5 * cm, 1.4 * cm, 'Sistema de Seguimiento de Egresados — UNDAC')
    canvas.drawRightString(A4[0] - 2.5 * cm, 1.4 * cm, f'Página {doc.page}')
    canvas.restoreState()


def _recomendaciones(d):
    total = d['total']
    sin_registro = d['situacion'][2][1]
    obs = []
    if _pct(sin_registro, total) > MAX_SIN_EMPLEO:
        obs.append(f'El {_pct(sin_registro, total)} % no registra ningún empleo. Se recomienda recordarles '
                   'completar su perfil laboral, aunque hoy no trabajen, para contar con información más completa.')
    if d['pct_titulados'] < MIN_TITULADOS:
        obs.append(f'Solo el {d["pct_titulados"]} % registra título profesional. Conviene verificar si falta '
                   'registrar el dato o si hay egresados a quienes orientar en el proceso de titulación.')
    if d['pct_participacion'] < MIN_PARTICIPACION:
        obs.append(f'El {d["pct_participacion"]} % respondió alguna encuesta. Se sugiere promover la '
                   'participación, por ejemplo con recordatorios y fechas límite claras.')
    if not obs:
        obs.append('Los indicadores principales superan los umbrales definidos; se recomienda mantener '
                   'las campañas de actualización de datos.')
    if total < MUESTRA_MINIMA:
        obs.insert(0, f'La cantidad de egresados considerados ({total}) es reducida: con pocos casos los '
                      'porcentajes varían mucho, por lo que deben interpretarse con cautela.')
    return obs


def generar_informe_pdf(d, filtros, generado_por):
    """Informe formal. `d` es el resultado de obtener_tablero(); `filtros`, la lista de criterios aplicados."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2.5 * cm, bottomMargin=2.5 * cm,
                            leftMargin=2.5 * cm, rightMargin=2.5 * cm,
                            title='Informe de seguimiento de egresados', author=generado_por)
    ancho = A4[0] - 5 * cm
    ahora = datetime.now(timezone(timedelta(hours=-5)))       # hora de Lima, sin depender del servidor
    fecha = f'{ahora.day} de {MESES[ahora.month - 1]} de {ahora.year}'
    total = d['total']
    criterios = '; '.join(filtros) if filtros else 'Todos los egresados registrados'

    # --- Encabezado y ficha ---
    ficha = Table([[Paragraph('<b>Criterios</b>', E['celda']), Paragraph(escape(criterios), E['celda'])],
                   [Paragraph('<b>Egresados considerados</b>', E['celda']), Paragraph(str(total), E['celda'])],
                   [Paragraph('<b>Fecha de emisión</b>', E['celda']), Paragraph(fecha, E['celda'])],
                   [Paragraph('<b>Elaborado por</b>', E['celda']), Paragraph(escape(generado_por), E['celda'])]],
                  colWidths=[4.5 * cm, ancho - 4.5 * cm])
    ficha.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    story = [Paragraph('INFORME DE SEGUIMIENTO DE EGRESADOS', E['titulo']),
             Paragraph('Escuela de Ingeniería de Sistemas y Computación — Universidad Nacional Daniel Alcides Carrión',
                       E['sub']),
             Spacer(1, 0.5 * cm), ficha, Spacer(1, 0.3 * cm), HRFlowable(width='100%', thickness=1, color=AZUL)]

    # --- 1. Introducción ---
    criterio_txt = (f'Para este informe se consideraron los egresados que cumplen con lo siguiente: '
                    f'{escape(criterios)}.' if filtros else
                    'Para este informe se consideraron todos los egresados registrados en el sistema, sin aplicar filtros.')
    story += [Paragraph('1. Introducción', E['h1']),
              _p('El presente informe resume la situación de los egresados de la Escuela de Ingeniería de '
                 'Sistemas y Computación de la Universidad Nacional Daniel Alcides Carrión (UNDAC), a partir de '
                 'la información que ellos mismos registran en el Sistema de Seguimiento de Egresados. Su '
                 'finalidad es ofrecer a la Escuela una visión de la empleabilidad, la formación posterior y la '
                 'participación de sus egresados, como apoyo para la toma de decisiones.'),
              _p(criterio_txt)]

    if total == 0:
        story += [_p('No hay egresados que cumplan con los criterios indicados, por lo que no es posible '
                     'presentar resultados. Se sugiere modificar los filtros e intentarlo nuevamente.')]
        doc.build(story, onFirstPage=_pie, onLaterPages=_pie)
        buf.seek(0)
        return buf

    # --- 2. Perfil ---
    v, m, sg = d['varones'], d['mujeres'], d['sin_genero']
    story += [Paragraph('2. Perfil de los egresados', E['h1']),
              _p(f'Cumplen con los criterios indicados <b>{_egr(total)}</b>. De ellos, {v} ({_pct(v, total)} %) '
                 f'son varones y {m} ({_pct(m, total)} %) son mujeres'
                 + (f'; de {sg} no se cuenta con el dato.' if sg else '.')),
              _tabla(['Género', 'Egresados', '% del total'],
                     [['Varones', v, f'{_pct(v, total)} %'], ['Mujeres', m, f'{_pct(m, total)} %']]
                     + ([['Sin dato', sg, f'{_pct(sg, total)} %']] if sg else []),
                     [ancho - 7 * cm, 3.5 * cm, 3.5 * cm], derecha=(1, 2))]

    # --- 3. Situación laboral ---
    actual, anteriores, sin_registro = (n for _, n in d['situacion'])
    story += [Paragraph('3. Situación laboral', E['h1']),
              _p(f'El {d["pct_empleo"]} % de los egresados ({_egr(actual)}) registra un empleo actual. '
                 f'Otros {anteriores} ({_pct(anteriores, total)} %) solo registran empleos anteriores y '
                 f'{sin_registro} ({_pct(sin_registro, total)} %) no ha registrado ninguno; esto último no '
                 'implica que estén desempleados, sino que no han completado esa parte de su perfil.'),
              _tabla(['Situación', 'Egresados', '% del total'],
                     [[nombre, n, f'{_pct(n, total)} %'] for nombre, n in d['situacion']],
                     [ancho - 7 * cm, 3.5 * cm, 3.5 * cm], derecha=(1, 2)),
              Spacer(1, 0.3 * cm)]

    sectores = d['sectores']
    if sectores:
        total_sec = sum(n for _, n in sectores)
        texto = (f'Entre los empleos actuales registrados, el sector con mayor presencia es '
                 f'«{escape(sectores[0][0])}», con {sectores[0][1]} ({_pct(sectores[0][1], total_sec)} %)')
        if len(sectores) > 1:
            texto += (f', seguido de «{escape(sectores[1][0])}», con {sectores[1][1]} '
                      f'({_pct(sectores[1][1], total_sec)} %)')
        story += [_p(texto + '.'),
                  _tabla(['Sector económico', 'Empleos actuales', '% de los empleos'],
                         [[s, n, f'{_pct(n, total_sec)} %'] for s, n in sectores],
                         [ancho - 7 * cm, 3.5 * cm, 3.5 * cm], derecha=(1, 2)),
                  Spacer(1, 0.3 * cm)]
    else:
        story.append(_p('Aún no hay empleos actuales registrados, por lo que no se puede mostrar la '
                        'distribución por sector económico.'))

    empresas = d['empresas']
    if empresas:
        story += [_p(f'La siguiente tabla presenta las '
                     f'{len(empresas)} instituciones principales, contando todos los empleos que los egresados registraron.'),
                  _tabla(['Empresa o institución', 'Egresados', '% del total'],
                         [[e, n, f'{_pct(n, total)} %'] for e, n in empresas],
                         [ancho - 7 * cm, 3.5 * cm, 3.5 * cm], derecha=(1, 2))]
    else:
        story.append(_p('Aún no hay empleos registrados, por lo que no se puede identificar en qué empresas '
                        'trabajan los egresados.'))

    # --- 4. Formación académica ---
    t = d['titulacion']
    bach, tit, mae, doct = t['datos']
    story += [Paragraph('4. Formación académica', E['h1']),
              _p(f'El {t["pct"][0]} % de los egresados tienen el grado de bachiller registrado y el '
                 f'{t["pct"][1]} % cuentan con título profesional. En estudios de posgrado '
                 f'{t["pct"][2]} % registran una maestría y {t["pct"][3]} % un doctorado. Un '
                 'mismo egresado puede figurar en más de una categoría.'),
              _tabla(['Grado o título', 'Egresados', '% del total'],
                     [[nombre, n, f'{p} %'] for nombre, n, p in zip(t['labels'], t['datos'], t['pct'])],
                     [ancho - 7 * cm, 3.5 * cm, 3.5 * cm], derecha=(1, 2))]

    # --- 5. Participación en encuestas ---
    story += [Paragraph('5. Participación en encuestas', E['h1']),
              _p(f'{_egr(d["participaron"])} ({d["pct_participacion"]} %) han respondido al menos una '
                 'encuesta del sistema.')]

    # --- 6. Detalle por currícula ---
    story += [Paragraph('6. Detalle por currícula', E['h1']),
              _p('La siguiente tabla desagrega los resultados según el plan de estudios (currícula) de cada egresado.'),
              _tabla(['Currícula', 'Con empleo', 'Egresados', 'Bachilleres', 'Titulados', 'Postgrados'],
                     [list(fila) for fila in d['curriculas']],
                     [ancho - 12.5 * cm] + [2.5 * cm] * 5, derecha=(1, 2, 3, 4, 5))]

    # --- 7. Conclusiones y recomendaciones ---
    story += [Paragraph('7. Conclusiones y recomendaciones', E['h1']),
              _p(f'En conjunto, de los {_egr(total)} considerados, el {d["pct_empleo"]} % registra un empleo '
                 f'actual, el {d["pct_titulados"]} % cuenta con título profesional y el '
                 f'{d["pct_participacion"]} % participó en alguna encuesta. Con base en estos resultados se plantea '
                 'lo siguiente:')]
    story += [Paragraph(o, E['vineta'], bulletText='•') for o in _recomendaciones(d)]

    doc.build(story, onFirstPage=_pie, onLaterPages=_pie)
    buf.seek(0)
    return buf