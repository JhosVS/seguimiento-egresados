# app/admin/informes.py
from datetime import datetime
from io import BytesIO

import matplotlib
matplotlib.use('Agg')   # sin ventanas: solo genera imágenes
import matplotlib.pyplot as plt
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

AZUL = RGBColor(0x00, 0x38, 0x76)
GRIS = RGBColor(0x6C, 0x75, 0x7D)
COLORES_NIVEL = ['#6c757d', '#0d6efd', '#198754', '#ffc107', '#dc3545']

TITULOS = {'nivel': 'Informe de nivel profesional',
           'participacion': 'Informe de participación en encuestas',
           'empleabilidad': 'Informe de empleabilidad'}


# ---------------------------------------------------------------- piezas reutilizables
def _nuevo_documento():
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.5)
    sec.top_margin = sec.bottom_margin = Cm(2.2)

    normal = doc.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(11)
    normal.paragraph_format.line_spacing = 1.3      # interlineado
    normal.paragraph_format.space_after = Pt(8)     # espacio entre párrafos

    for nombre, tam in (('Title', 22), ('Heading 1', 14)):
        e = doc.styles[nombre]
        e.font.name = 'Calibri'
        e.font.size = Pt(tam)
        e.font.color.rgb = AZUL
        e.paragraph_format.space_before = Pt(16 if nombre == 'Heading 1' else 0)
        e.paragraph_format.space_after = Pt(6)

    # Pie de página con número de página
    pie = sec.footer.paragraphs[0]
    pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = pie.add_run('Sistema de Seguimiento de Egresados · Página ')
    r.font.size = Pt(9)
    r.font.color.rgb = GRIS
    run = pie.add_run()
    run.font.size = Pt(9)
    for tipo, texto in (('begin', None), (None, 'PAGE'), ('end', None)):
        if tipo:
            el = OxmlElement('w:fldChar')
            el.set(qn('w:fldCharType'), tipo)
        else:
            el = OxmlElement('w:instrText')
            el.text = texto
        run._r.append(el)
    return doc


def _nota(doc, texto):
    p = doc.add_paragraph()
    r = p.add_run(texto)
    r.font.size = Pt(9)
    r.font.color.rgb = GRIS
    return p


def _pintar_celda(celda, color_hex):
    tcPr = celda._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:fill'), color_hex)
    tcPr.append(shd)


def _escribir(celda, texto, negrita=False, derecha=False, color=None, tam=10):
    p = celda.paragraphs[0]
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.15
    if derecha:
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = p.add_run(str(texto))
    r.bold = negrita
    r.font.size = Pt(tam)
    if color:
        r.font.color.rgb = color


def _kpis(doc, items):
    """Fila de indicadores: items = [(valor, etiqueta), ...]."""
    t = doc.add_table(rows=1, cols=len(items))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for celda, (valor, etiqueta) in zip(t.rows[0].cells, items):
        _pintar_celda(celda, 'F1F3F5')
        p = celda.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(str(valor))
        r.bold = True
        r.font.size = Pt(18)
        r.font.color.rgb = AZUL
        p2 = celda.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2.paragraph_format.space_after = Pt(8)
        r2 = p2.add_run(etiqueta)
        r2.font.size = Pt(9)
        r2.font.color.rgb = GRIS
    doc.add_paragraph()   # aire debajo


def _tabla(doc, cabecera, filas, anchos_cm, total=None):
    """Tabla simple: primera columna a la izquierda, el resto a la derecha."""
    t = doc.add_table(rows=1, cols=len(cabecera))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False

    for i, texto in enumerate(cabecera):
        celda = t.rows[0].cells[i]
        _pintar_celda(celda, '003876')
        _escribir(celda, texto, negrita=True, derecha=i > 0, color=RGBColor(255, 255, 255))

    for fila in filas:
        celdas = t.add_row().cells
        for i, v in enumerate(fila):
            _escribir(celdas[i], v, derecha=i > 0)

    if total:
        celdas = t.add_row().cells
        for i, v in enumerate(total):
            _pintar_celda(celdas[i], 'F1F3F5')
            _escribir(celdas[i], v, negrita=True, derecha=i > 0)

    for fila in t.rows:
        for celda, ancho in zip(fila.cells, anchos_cm):
            celda.width = Cm(ancho)
    doc.add_paragraph()   # aire debajo
    return t


def _imagen(doc, fig, ancho_cm=15):
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    doc.add_picture(buf, width=Cm(ancho_cm))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER


def _recortar(texto, n=38):
    return texto if len(texto) <= n else texto[:n - 1] + '…'


def _grafico_barras(doc, etiquetas, valores, colores=None, horizontal=False):
    etiquetas = [_recortar(e) for e in etiquetas]
    if horizontal:   # el mayor queda arriba
        etiquetas, valores = etiquetas[::-1], valores[::-1]
        colores = colores[::-1] if colores else None
    alto = max(2.6, len(etiquetas) * 0.4 + 0.8) if horizontal else 3.4
    fig, ax = plt.subplots(figsize=(7, alto))
    barras = (ax.barh if horizontal else ax.bar)(etiquetas, valores, color=colores or '#0d6efd')
    ax.bar_label(barras, padding=3, fontsize=9)
    for lado in ('top', 'right'):
        ax.spines[lado].set_visible(False)
    eje = ax.xaxis if horizontal else ax.yaxis
    eje.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.tick_params(labelsize=9)
    if not horizontal:
        plt.setp(ax.get_xticklabels(), rotation=15, ha='right')
    _imagen(doc, fig)


def _grafico_circular(doc, valores, etiquetas):
    fig, ax = plt.subplots(figsize=(4.5, 3.2))
    ax.pie(valores, labels=[f'{e}: {v}' for e, v in zip(etiquetas, valores)],
           colors=['#198754', '#dee2e6'], startangle=90, counterclock=False,
           autopct=lambda p: f'{p:.0f}%' if p > 0 else '',
           wedgeprops={'width': 0.45, 'edgecolor': 'white'}, textprops={'fontsize': 9})
    _imagen(doc, fig, ancho_cm=10)


def _sin_datos(doc, texto='No hay egresados con estos filtros.'):
    doc.add_paragraph(texto)


# ---------------------------------------------------------------- bloques comunes
def _que_contiene(doc, texto):
    doc.add_heading('Qué contiene este informe', level=1)
    doc.add_paragraph(texto)


def _filtros(doc, filtros):
    doc.add_heading('Filtros aplicados', level=1)
    doc.add_paragraph(' · '.join(filtros) if filtros
                      else 'Ninguno: se incluye a todos los egresados registrados en el sistema.')


def _observaciones(doc):
    doc.add_heading('Observaciones y conclusiones', level=1)
    _nota(doc, 'Espacio para completar a mano antes de presentar el informe.')
    for _ in range(3):
        doc.add_paragraph('_' * 85)


# ---------------------------------------------------------------- un informe por pestaña
def _informe_nivel(doc, d, filtros):
    _que_contiene(doc,
        'Este informe muestra cuántos egresados hay registrados y cuál es el nivel profesional más alto que '
        'alcanzó cada uno: solo egresado (sin grado ni título registrado), bachiller, título profesional, '
        'maestría o doctorado. Cada egresado se cuenta una sola vez, según su nivel máximo. Incluye el total, '
        'su distribución por género, un gráfico de barras y una tabla con cantidades y porcentajes.')
    _filtros(doc, filtros)
    if d['total'] == 0:
        return _sin_datos(doc)

    doc.add_heading('Indicadores', level=1)
    _kpis(doc, [(d['total'], 'Total de egresados'),
                (f'{d["varones"]} ({d["pct_varones"]}%)', 'Masculino'),
                (f'{d["mujeres"]} ({d["pct_mujeres"]}%)', 'Femenino')])
    if d['sin_genero']:
        _nota(doc, f'Egresados sin género registrado: {d["sin_genero"]}.')

    doc.add_heading('Egresados por nivel profesional', level=1)
    _grafico_barras(doc, d['labels'], d['datos'], COLORES_NIVEL)
    _tabla(doc, ['Nivel máximo alcanzado', 'Egresados', '% del total'],
           [[n, c, f'{p}%'] for n, c, p in zip(d['labels'], d['datos'], d['pct'])],
           [8, 3.5, 3.5], total=['Total', d['total'], '100%'])


def _informe_participacion(doc, d, filtros):
    _que_contiene(doc,
        'Este informe muestra cuántos egresados respondieron la encuesta seleccionada y cuántos faltan. '
        'Incluye el porcentaje de participación, un gráfico circular y una tabla que separa a los egresados '
        'según su nivel profesional máximo (solo egresados, bachilleres, titulados y maestría o doctorado), '
        'para identificar qué grupos participan menos.')
    _filtros(doc, filtros)
    if not d['encuesta']:
        return _sin_datos(doc, 'No hay encuestas publicadas todavía.')
    if d['total'] == 0:
        return _sin_datos(doc)

    doc.add_heading(f'Encuesta: {d["encuesta"].nombre} ({d["encuesta"].anio})', level=1)
    _kpis(doc, [(f'{d["pct"]}%', 'Participación'),
                (d['respondieron'], 'Respondieron'),
                (d['faltan'], 'Pendientes')])
    _grafico_circular(doc, [d['respondieron'], d['faltan']], ['Respondieron', 'Pendientes'])

    doc.add_heading('Participación según nivel máximo', level=1)
    _tabla(doc, ['Nivel', 'Respondieron', 'Total', 'Faltan'], d['filas'], [6, 3.5, 3, 3],
           total=['Total', d['respondieron'], d['total'], d['faltan']])


def _informe_empleabilidad(doc, d, filtros, actual):
    _que_contiene(doc,
        'Este informe muestra cuántos egresados tienen un empleo actual registrado y cuántos no, en qué '
        'sectores económicos trabajan y cuáles son las 10 empresas donde más egresados han trabajado. ' +
        ('Por el filtro "Solo empleo actual", el sector y las empresas consideran únicamente empleos vigentes.'
         if actual else
         'El sector y las empresas consideran todo el historial de empleos registrados, actuales o anteriores.'))
    _filtros(doc, filtros)
    if d['total'] == 0:
        return _sin_datos(doc)

    doc.add_heading('Indicadores', level=1)
    _kpis(doc, [(d['total'], 'Egresados'),
                (f'{d["con_empleo"]} ({d["pct_con"]}%)', 'Con empleo actual'),
                (f'{d["sin_empleo"]} ({d["pct_sin"]}%)', 'Sin empleo actual')])
    _nota(doc, '"Sin empleo actual" no significa necesariamente desempleo: solo indica que el egresado no '
               'tiene un empleo actual registrado en el sistema.')

    doc.add_heading('Egresados por sector (empleo actual)' if actual else 'Egresados por sector (historial)', level=1)
    if d['sectores']:
        _tabla(doc, ['Sector', 'Egresados'], [[s, n] for _, s, n in d['sectores']], [12, 4])
        if not actual:
            _nota(doc, 'Un egresado puede figurar en varios sectores si trabajó en más de uno; por eso la suma '
                       'puede superar el total.')
    else:
        doc.add_paragraph('Sin empleos registrados con estos filtros.')

    doc.add_heading('Top 10 empresas donde trabajan actualmente' if actual
                    else 'Top 10 empresas donde han trabajado', level=1)
    if d['empresas']:
        _grafico_barras(doc, [e[0] for e in d['empresas']], [e[1] for e in d['empresas']], horizontal=True)
    else:
        doc.add_paragraph('Sin datos con estos filtros.')


def generar_informe(vista, datos, f, filtros, autor):
    """Devuelve el Word (BytesIO) del informe de la pestaña indicada."""
    doc = _nuevo_documento()
    doc.add_heading(TITULOS[vista], level=0)
    _nota(doc, f'Generado el {datetime.now():%d/%m/%Y a las %H:%M} por {autor}.')

    if vista == 'nivel':
        _informe_nivel(doc, datos, filtros)
    elif vista == 'participacion':
        _informe_participacion(doc, datos, filtros)
    else:
        _informe_empleabilidad(doc, datos, filtros, f['actual'])
    _observaciones(doc)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf