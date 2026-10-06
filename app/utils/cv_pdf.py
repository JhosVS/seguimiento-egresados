# app/utils/cv_pdf.py
import io
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from urllib.parse import unquote

AZUL       = colors.HexColor('#003876')
AZUL_CLARO = colors.HexColor('#e8f0fe')
GRIS       = colors.HexColor('#64748b')
NEGRO      = colors.HexColor('#1e293b')

ANCHO_SIDEBAR = 6 * cm
INDENT = 8  # indentación moderada, en puntos


# ------------------------------------------------------------
# ESTILOS
# ------------------------------------------------------------
def _estilo_seccion_lateral():
    return ParagraphStyle('SeccionLateral', fontSize=10, textColor=AZUL, fontName='Helvetica-Bold', spaceBefore=14, spaceAfter=6)

def _estilo_seccion_principal():
    return ParagraphStyle('SeccionPrincipal', fontSize=12, textColor=AZUL, fontName='Helvetica-Bold', spaceBefore=16, spaceAfter=6)

def _estilo_lateral_texto():
    return ParagraphStyle('LateralTexto', fontSize=8.5, textColor=NEGRO, leading=13, leftIndent=INDENT, spaceAfter=4)

def _estilo_lateral_bullet():
    return ParagraphStyle('LateralBullet', fontSize=8.5, textColor=NEGRO, leading=13, leftIndent=INDENT, spaceAfter=3)

def _estilo_normal():
    return ParagraphStyle('Normal2', fontSize=9.5, textColor=NEGRO, leading=14)

def _estilo_item_titulo():
    return ParagraphStyle('ItemTitulo', fontSize=9.5, textColor=NEGRO, fontName='Helvetica-Bold', leading=13, spaceBefore=4)

def _estilo_item_sub():
    return ParagraphStyle('ItemSub', fontSize=8, textColor=GRIS, leading=12, leftIndent=INDENT)

def _estilo_item_bullet():
    return ParagraphStyle('ItemBullet', fontSize=8.5, textColor=NEGRO, leading=12.5, leftIndent=INDENT + 4, spaceAfter=1)

# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def _foto_circular(ruta_relativa, diametro_px=600):
    """Genera una versión circular de la foto en memoria usando PIL."""
    if not ruta_relativa:
        return None
    ruta_disco = os.path.join('app', 'static', ruta_relativa)
    if not os.path.exists(ruta_disco):
        return None
    try:
        from PIL import Image as PILImage, ImageDraw
        im = PILImage.open(ruta_disco).convert('RGBA')
        lado = min(im.size)
        im = im.crop((
            (im.width - lado) // 2, (im.height - lado) // 2,
            (im.width + lado) // 2, (im.height + lado) // 2
        )).resize((diametro_px, diametro_px))

        mask = PILImage.new('L', (diametro_px, diametro_px), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, diametro_px, diametro_px), fill=255)

        salida = PILImage.new('RGBA', (diametro_px, diametro_px), (0, 0, 0, 0))
        salida.paste(im, (0, 0), mask)

        buf_img = io.BytesIO()
        salida.save(buf_img, format='PNG')
        buf_img.seek(0)

        tam = 5.4 * cm
        img = Image(buf_img, width=tam, height=tam)
        return img
    except Exception:
        return None

def _lineas_a_bullets(texto):
    """Convierte texto con saltos de línea/guiones en lista de strings limpios."""
    if not texto:
        return []
    lineas = [l.strip(' -•\t') for l in texto.split('\n')]
    return [l for l in lineas if l]


def _sugerir_titulo(egresado):
    mapa = {
        'egresado':  'Egresado de Ingeniería de Sistemas y Computación',
        'bachiller': 'Bachiller en Ciencias de Ingeniería de Sistemas y Computación',
        'titulado':  'Ingeniero de Sistemas y Computación',
        'maestria':  'Magíster',
        'doctorado': 'Doctor',
        'phd':       'PhD',
    }
    return mapa.get(egresado.nivel_maximo, 'Egresado de Ingeniería de Sistemas y Computación')

def _extraer_identificador(url, red=None):
    """Extrae el nombre de usuario/perfil legible de una URL."""
    if not url:
        return None
    limpio = url.rstrip('/')

    if red == 'linkedin' and '/in/' in limpio:
        despues_in = limpio.split('/in/')[-1]
        segmento = despues_in.split('/')[0]
        return unquote(segmento)

    partes = limpio.split('/')
    identificador = partes[-1] if partes else limpio
    if not identificador or ('.' in identificador and len(partes) <= 3):
        identificador = limpio.replace('https://', '').replace('http://', '')
    return unquote(identificador)

def _procesar_idiomas(idiomas):
    """Arma la lista final de idiomas para el CV."""
    orden_nivel = {'basico': 1, 'intermedio': 2, 'avanzado': 3}

    mejores = {}
    for idi in idiomas:
        nombre = (getattr(idi, 'nombre', '') or '').strip()
        clave  = nombre.lower()
        if clave in ('español', 'espanol'):
            continue

        nivel_idioma = getattr(idi, 'nivel_idioma', '') or ''
        nivel_actual = orden_nivel.get(nivel_idioma.lower(), 0)
        if clave not in mejores or nivel_actual > mejores[clave][1]:
            mejores[clave] = (idi, nivel_actual)

    resultado = [('Español', 'Nativo')]
    for idi, _ in mejores.values():
        nivel_raw = getattr(idi, 'nivel_idioma', '') or ''
        nivel = nivel_raw.capitalize() if nivel_raw else ''
        resultado.append((getattr(idi, 'nombre', ''), nivel))

    return resultado

# ------------------------------------------------------------
# GENERADOR PRINCIPAL
# ------------------------------------------------------------
def generar_cv(egresado, empleos, logros, certificados,
                habilidades=None, intereses=None, idiomas=None):
    habilidades = habilidades or []
    intereses   = intereses or []
    idiomas     = idiomas or []

    buf    = io.BytesIO()
    W, H   = A4
    margen = 1.3 * cm
    ancho  = W - 2 * margen

    doc = SimpleDocTemplate(buf, pagesize=A4,
                             topMargin=margen, bottomMargin=margen,
                             leftMargin=margen, rightMargin=margen)
    story = []

    nombre_completo = (f"{egresado.nombres} {egresado.apellido_paterno} "
                        f"{egresado.apellido_materno or ''}").strip()
    titulo_cv = egresado.titulo_cv or _sugerir_titulo(egresado)

    # ============================================================
    # COLUMNA IZQUIERDA (SIDEBAR)
    # ============================================================
    sidebar = []

    foto = _foto_circular(egresado.foto)
    if foto:
        sidebar.append(foto)
        sidebar.append(Spacer(1, 0.4*cm))

    # Contacto
    sidebar.append(Paragraph('CONTACTO', _estilo_seccion_lateral()))
    if egresado.telefono:
        sidebar.append(Paragraph(f'<b>Teléfono:</b> {egresado.telefono}', _estilo_lateral_texto()))
    correo = egresado.correo_personal or egresado.correo_institucional
    if correo:
        sidebar.append(Paragraph(f'<b>E-mail:</b> {correo}', _estilo_lateral_texto()))
    if egresado.distrito or egresado.provincia:
        lugar = ', '.join(filter(None, [egresado.distrito, egresado.provincia]))
        sidebar.append(Paragraph(f'<b>Dirección:</b> {lugar}', _estilo_lateral_texto()))

    # Habilidades
    if habilidades:
        sidebar.append(Paragraph('HABILIDADES', _estilo_seccion_lateral()))
        for h in habilidades:
            sidebar.append(Paragraph(f'• {h.nombre}', _estilo_lateral_bullet()))

    # Idiomas
    idiomas_finales = _procesar_idiomas(idiomas)
    if idiomas_finales:
        sidebar.append(Paragraph('IDIOMAS', _estilo_seccion_lateral()))
        for nombre, nivel in idiomas_finales:
            texto = f'• {nombre}' + (f' — {nivel}' if nivel else '')
            sidebar.append(Paragraph(texto, _estilo_lateral_bullet()))

    # Intereses
    if intereses:
        sidebar.append(Paragraph('INTERESES', _estilo_seccion_lateral()))
        for it in intereses:
            sidebar.append(Paragraph(f'• {it.nombre}', _estilo_lateral_bullet()))

    # Redes sociales
    redes = []
    if egresado.linkedin:
        redes.append(('LinkedIn', _extraer_identificador(egresado.linkedin, red='linkedin')))
    if egresado.facebook:
        redes.append(('Facebook', _extraer_identificador(egresado.facebook)))
    if egresado.tiktok:
        redes.append(('TikTok', egresado.tiktok.replace('@', '')))

    if redes:
        sidebar.append(Paragraph('REDES SOCIALES', _estilo_seccion_lateral()))
        for plataforma, valor in redes:
            sidebar.append(Paragraph(f'• {plataforma}: {valor}', _estilo_lateral_bullet()))

    # ============================================================
    # COLUMNA DERECHA (PRINCIPAL)
    # ============================================================
    principal = []

    principal.append(Paragraph(
        nombre_completo,
        ParagraphStyle('Nombre', fontSize=19, leading=21, textColor=AZUL,
                       fontName='Helvetica-Bold', spaceAfter=8)
    ))
    principal.append(Paragraph(
        titulo_cv,
        ParagraphStyle('Titulo', fontSize=11, textColor=GRIS, spaceAfter=12)
    ))
    principal.append(HRFlowable(width='100%', thickness=1.2, color=AZUL))
    principal.append(Spacer(1, 0.3*cm))

    # Perfil
    if egresado.perfil_profesional:
        principal.append(Paragraph('PERFIL', _estilo_seccion_principal()))
        principal.append(Paragraph(egresado.perfil_profesional, _estilo_normal()))

    # Formación profesional
    if logros:
        principal.append(Paragraph('FORMACIÓN PROFESIONAL', _estilo_seccion_principal()))
        for l in logros:
            principal.append(Paragraph(l.grado_titulo, _estilo_item_titulo()))
            fecha = l.fecha_obtencion.strftime('%d/%m/%Y') if l.fecha_obtencion else '—'
            principal.append(Paragraph(f'{l.institucion} · {fecha}', _estilo_item_sub()))
            principal.append(Spacer(1, 0.15*cm))

    # Experiencia laboral
    if empleos:
        principal.append(Paragraph('EXPERIENCIA PROFESIONAL', _estilo_seccion_principal()))
        for emp in empleos:
            # CORRECCIÓN DE LA EMPRESA
            if hasattr(emp, 'empresa_nombre') and emp.empresa_nombre:
                empresa_nombre = emp.empresa_nombre
            elif hasattr(emp, 'empresa') and emp.empresa:
                empresa_nombre = emp.empresa.nombre if hasattr(emp.empresa, 'nombre') else str(emp.empresa)
            else:
                empresa_nombre = '—'

            principal.append(Paragraph(f'{emp.cargo} — {empresa_nombre}', _estilo_item_titulo()))
            inicio = emp.fecha_inicio.strftime('%m/%Y') if emp.fecha_inicio else '—'
            if emp.es_actual:
                rango = f'{inicio} – Presente'
            else:
                fin = emp.fecha_fin.strftime('%m/%Y') if emp.fecha_fin else '—'
                rango = f'{inicio} – {fin}'
            principal.append(Paragraph(rango, _estilo_item_sub()))

            for linea in _lineas_a_bullets(emp.funciones):
                principal.append(Paragraph(f'• {linea}', _estilo_item_bullet()))

            principal.append(Spacer(1, 0.2*cm))

    # Certificaciones
    if certificados:
        principal.append(Paragraph('CERTIFICACIONES Y CAPACITACIONES', _estilo_seccion_principal()))
        for c in certificados:
            # Obtener el nombre base del certificado
            nombre_cert = c.nombre_mostrar() if hasattr(c, 'nombre_mostrar') and callable(getattr(c, 'nombre_mostrar')) else getattr(c, 'nombre', '')

            # Extraer nivel si aplica (soporta atributos 'nivel_idioma' o 'nivel')
            nivel = getattr(c, 'nivel_idioma', None) or getattr(c, 'nivel', None)
            if nivel:
                nombre_cert = f"{nombre_cert} — {str(nivel).capitalize()}"

            principal.append(Paragraph(nombre_cert, _estilo_item_titulo()))
            fecha = c.fecha_emision.strftime('%m/%Y') if c.fecha_emision else '—'
            principal.append(Paragraph(f'{c.institucion_emisora} · {fecha}', _estilo_item_sub()))
            principal.append(Spacer(1, 0.15*cm))

    # ============================================================
    # ENSAMBLAJE
    # ============================================================
    ancho_principal = ancho - ANCHO_SIDEBAR

    tabla_layout = Table(
        [[sidebar, principal]],
        colWidths=[ANCHO_SIDEBAR, ancho_principal]
    )
    tabla_layout.setStyle(TableStyle([
        ('VALIGN',        (0,0), (0,0), 'TOP'),
        ('VALIGN',        (1,0), (1,0), 'TOP'),
        ('BACKGROUND',    (0,0), (0,0), AZUL_CLARO),
        ('LEFTPADDING',   (0,0), (0,0), 10),
        ('RIGHTPADDING',  (0,0), (0,0), 10),
        ('TOPPADDING',    (0,0), (0,0), 12),
        ('BOTTOMPADDING', (0,0), (0,0), 12),
        ('LEFTPADDING',   (1,0), (1,0), 14),
        ('RIGHTPADDING',  (1,0), (1,0), 4),
        ('TOPPADDING',    (1,0), (1,0), 4),
    ]))
    story.append(tabla_layout)

    # Pie de página compacto alineado a la derecha
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width=ancho, thickness=0.5, color=GRIS))
    story.append(Spacer(1, 0.15*cm))
    
    fecha_gen = datetime.now().strftime('%d/%m/%Y')
    
    from reportlab.lib.enums import TA_RIGHT
    
    story.append(Paragraph(
        f'CV Generado el {fecha_gen}',
        ParagraphStyle('Pie', fontSize=7.5, textColor=GRIS, alignment=TA_RIGHT)
    ))

    doc.build(story)
    buf.seek(0)
    return buf