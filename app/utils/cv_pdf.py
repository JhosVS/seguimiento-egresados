# app/utils/cv_pdf.py
import io
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, SimpleDocTemplate, PageTemplate, Frame, Paragraph,
    Spacer, Table, TableStyle, Image, FrameBreak, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_JUSTIFY, TA_CENTER, TA_LEFT
from urllib.parse import unquote
from reportlab.lib.units import cm
from xml.sax.saxutils import escape as _esc

# ------------------------------------------------------------
# PALETA DE COLORES (CV PRINCIPAL)
# ------------------------------------------------------------
COLOR_TEXTO   = colors.HexColor('#292524')  # Charcoal cálido
COLOR_TITULO  = colors.HexColor('#1c1917')  # Dark charcoal para nombres
COLOR_GRIS    = colors.HexColor('#78716c')  # Taupe / Gris cálido para fechas y subtítulos
COLOR_SIDEBAR = colors.HexColor('#f4f1ea')  # Crema suave (Fondo lateral)

ANCHO_SIDEBAR_PT = 185  # ~6.5 cm
ANCHO_PAGINA, ALTO_PAGINA = A4

# ------------------------------------------------------------
# ESTILOS TIPOGRÁFICOS SANS-SERIF (CV PRINCIPAL - INTACTO)
# ------------------------------------------------------------
def _estilo(name, **kwargs):
    defaults = dict(fontName='Helvetica', fontSize=9.5, textColor=COLOR_TEXTO, leading=14)
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)

ESTILOS = {
    'nombre': _estilo('Nombre', fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=COLOR_TITULO, spaceAfter=3),
    'titulo_cv': _estilo('TitCV', fontName='Helvetica-Oblique', fontSize=10, textColor=COLOR_GRIS, spaceAfter=12),
    'perfil': _estilo('Perfil', fontName='Helvetica', fontSize=9, leading=14.5, textColor=COLOR_TEXTO, alignment=TA_JUSTIFY, spaceAfter=12),
    'sec_lat': _estilo('SecLat', fontName='Helvetica-Bold', fontSize=9.5, textColor=COLOR_TITULO, spaceBefore=14, spaceAfter=6),
    'txt_lat': _estilo('TxtLat', fontName='Helvetica', fontSize=8.5, leading=12.5, spaceAfter=4),
    'sec_main': _estilo('SecMain', fontName='Helvetica-Bold', fontSize=10.5, textColor=COLOR_TITULO, spaceBefore=0, spaceAfter=0),
    'item_tit': _estilo('ItemTit', fontName='Helvetica-Bold', fontSize=9.5, leading=13, textColor=COLOR_TEXTO, leftIndent=12),
    'item_sub': _estilo('ItemSub', fontName='Helvetica', fontSize=8.5, leading=12, textColor=COLOR_GRIS, leftIndent=12, spaceAfter=2),
    'item_bol': _estilo('ItemBol', fontName='Helvetica', fontSize=8.5, leading=13, leftIndent=22, spaceAfter=2),
    'fecha_der': _estilo('FechaDer', fontName='Helvetica-Oblique', fontSize=8, textColor=COLOR_GRIS, alignment=TA_RIGHT),
}

# ------------------------------------------------------------
# FONDO LATERAL COMPLETO (CV PRINCIPAL)
# ------------------------------------------------------------
def _dibujar_fondo_sidebar(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(COLOR_SIDEBAR)
    canvas.rect(0, 0, ANCHO_SIDEBAR_PT, ALTO_PAGINA, fill=1, stroke=0)
    canvas.restoreState()

# ------------------------------------------------------------
# HELPERS Y FORMATEADORES DE FECHA EN ESPAÑOL
# ------------------------------------------------------------
MESES_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}

def _formatear_fecha(fecha):
    if not fecha:
        return ''
    mes = MESES_ES.get(fecha.month, '')
    return f"{mes} {fecha.year}" if mes else str(fecha.year)

def _icono_flecha():
    from PIL import Image as PILImage, ImageDraw
    size = 24
    im = PILImage.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    color = '#1c1917'
    draw.polygon([(6, 6), (18, 12), (6, 18)], fill=color)
    buf = io.BytesIO()
    im.save(buf, format='PNG')
    buf.seek(0)
    return Image(buf, width=10, height=10)

def _seccion_con_icono(titulo_texto):
    t = Table([[_icono_flecha(), Paragraph(titulo_texto, ESTILOS['sec_main'])]], colWidths=[14, None])
    t.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    from reportlab.platypus import KeepTogether
    return KeepTogether([Spacer(1, 14), t, Spacer(1, 6)])

def _icono_contacto(tipo):
    from PIL import Image as PILImage, ImageDraw
    size = 28
    im = PILImage.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    color = '#1c1917'
    
    if tipo == 'phone':
        draw.rounded_rectangle([8, 4, 20, 24], radius=3, outline=color, width=2)
        draw.line([12, 20, 16, 20], fill=color, width=2)
    elif tipo == 'email':
        draw.rectangle([4, 7, 24, 21], outline=color, width=2)
        draw.line([4, 7, 14, 15], fill=color, width=2)
        draw.line([24, 7, 14, 15], fill=color, width=2)
    elif tipo == 'location':
        draw.ellipse([8, 4, 20, 16], outline=color, width=2)
        draw.polygon([[14, 24], [8, 14], [20, 14]], outline=color, fill=None)
    elif tipo == 'linkedin':
        draw.rounded_rectangle([5, 5, 23, 23], radius=3, outline=color, width=2)
        draw.ellipse([8, 9, 11, 12], fill=color)
        draw.line([9, 14, 9, 20], fill=color, width=2)
        draw.line([14, 14, 14, 20], fill=color, width=2)
        draw.arc([14, 13, 19, 20], start=270, end=90, fill=color, width=2)

    buf = io.BytesIO()
    im.save(buf, format='PNG')
    buf.seek(0)
    return Image(buf, width=11, height=11)

def _formatear_texto(texto):
    if not texto: return ''
    if texto.isupper() and len(texto) > 5:
        return texto.title()
    return texto

def _foto_circular(ruta_relativa, diametro_px=600):
    if not ruta_relativa:
        return None
    ruta_disco = os.path.join('app', 'static', ruta_relativa)
    if not os.path.exists(ruta_disco):
        return None
    try:
        from PIL import Image as PILImage, ImageDraw
        im = PILImage.open(ruta_disco).convert('RGBA')
        lado = min(im.size)
        im = im.crop(((im.width - lado)//2, (im.height - lado)//2, (im.width + lado)//2, (im.height + lado)//2)).resize((diametro_px, diametro_px))
        
        mask = PILImage.new('L', (diametro_px, diametro_px), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, diametro_px, diametro_px), fill=255)
        
        foto_circ = PILImage.new('RGBA', (diametro_px, diametro_px), (0,0,0,0))
        foto_circ.paste(im, (0, 0), mask)
        
        grosor_marco = 24
        tam_final = diametro_px + (grosor_marco * 2)
        lienzo = PILImage.new('RGBA', (tam_final, tam_final), (0,0,0,0))
        draw = ImageDraw.Draw(lienzo)
        
        draw.ellipse((0, 0, tam_final - 1, tam_final - 1), outline='#a8a29e', width=6)
        offset_in = 8
        draw.ellipse((offset_in, offset_in, tam_final - 1 - offset_in, tam_final - 1 - offset_in), outline='#ffffff', width=8)
        
        lienzo.paste(foto_circ, (grosor_marco, grosor_marco), foto_circ)
        
        buf_img = io.BytesIO()
        lienzo.save(buf_img, format='PNG')
        buf_img.seek(0)
        return Image(buf_img, width=130, height=130)
    except Exception:
        return None

def _lineas_a_bullets(texto):
    if not texto: return []
    return [l.strip(' -•\t') for l in texto.split('\n') if l.strip(' -•\t')]

def _sugerir_titulo(egresado):
    mapa = {'egresado': 'Egresado de Ingeniería', 'bachiller': 'Bachiller en Ingeniería', 'titulado': 'Ingeniero', 'maestria': 'Magíster', 'doctorado': 'Doctor'}
    return mapa.get(egresado.nivel_maximo, 'Profesional en Ingeniería')

def _extraer_identificador(url, red=None):
    if not url: return None
    limpio = url.rstrip('/')
    if red == 'linkedin' and '/in/' in limpio:
        return unquote(limpio.split('/in/')[-1].split('/')[0])
    return unquote(limpio.split('/')[-1] or limpio)

def _procesar_idiomas(idiomas):
    resultado = [('Español', 'Nativo')]
    for idi in idiomas:
        nombre = (getattr(idi, 'nombre', '') or '').strip()
        if nombre and nombre.lower() not in ('español', 'espanol'):
            resultado.append((nombre, (getattr(idi, 'nivel_idioma', '') or '').capitalize()))
    return resultado

def _correo_contacto(egresado):
    if egresado.correo_personal:
        return egresado.correo_personal
    return egresado.usuario.correo if egresado.usuario else None

# ------------------------------------------------------------
# GENERADOR PRINCIPAL (CV CON SIDEBAR)
# ------------------------------------------------------------
def generar_cv(egresado, empleos, logros, certificados, habilidades=None, intereses=None, idiomas=None, titulo=None, perfil=None):
    habilidades, intereses, idiomas = habilidades or [], intereses or [], idiomas or []
    buf = io.BytesIO()
    
    doc = BaseDocTemplate(
        buf, pagesize=A4, leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0
    )

    frame_sidebar = Frame(
        x1=12, y1=15, 
        width=ANCHO_SIDEBAR_PT - 20, height=ALTO_PAGINA - 30,
        id='frame_sidebar',
        topPadding=15, bottomPadding=15, leftPadding=12, rightPadding=8
    )

    x_inicio_main = ANCHO_SIDEBAR_PT + 15
    ancho_neto_main = ANCHO_PAGINA - x_inicio_main - 20
    
    frame_main = Frame(
        x1=x_inicio_main, y1=15,
        width=ancho_neto_main, height=ALTO_PAGINA - 30,
        id='frame_main',
        topPadding=20, bottomPadding=15, leftPadding=12, rightPadding=15
    )

    doc.addPageTemplates([
        PageTemplate(
            id='CV_Layout',
            frames=[frame_sidebar, frame_main],
            onPage=_dibujar_fondo_sidebar
        )
    ])

    story = []

    foto = _foto_circular(egresado.foto)
    if foto:
        story.append(foto)
        story.append(Spacer(1, 10))

    story.append(Paragraph('CONTACTO', ESTILOS['sec_lat']))
    
    ancho_col_icono = 18
    ancho_col_texto = ANCHO_SIDEBAR_PT - 45

    if egresado.telefono:
        t_item = Table([[_icono_contacto('phone'), Paragraph(egresado.telefono, ESTILOS['txt_lat'])]], colWidths=[ancho_col_icono, ancho_col_texto])
        t_item.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 2), ('TOPPADDING', (0,0), (-1,-1), 2)]))
        story.append(t_item)

    correo = _correo_contacto(egresado)
    if correo:
        t_item = Table([[_icono_contacto('email'), Paragraph(correo, ESTILOS['txt_lat'])]], colWidths=[ancho_col_icono, ancho_col_texto])
        t_item.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 2), ('TOPPADDING', (0,0), (-1,-1), 2)]))
        story.append(t_item)

    if egresado.distrito or egresado.provincia:
        loc = ", ".join(filter(None, [egresado.distrito, egresado.provincia]))
        t_item = Table([[_icono_contacto('location'), Paragraph(loc, ESTILOS['txt_lat'])]], colWidths=[ancho_col_icono, ancho_col_texto])
        t_item.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 2), ('TOPPADDING', (0,0), (-1,-1), 2)]))
        story.append(t_item)

    if egresado.linkedin:
        url_lk = egresado.linkedin if egresado.linkedin.startswith(('http://', 'https://')) else 'https://' + egresado.linkedin
        txt_lk = _extraer_identificador(egresado.linkedin, "linkedin")
        link_lk = f'<a href="{url_lk}">{txt_lk}</a>'
        t_item = Table([[_icono_contacto('linkedin'), Paragraph(link_lk, ESTILOS['txt_lat'])]], colWidths=[ancho_col_icono, ancho_col_texto])
        t_item.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 2), ('TOPPADDING', (0,0), (-1,-1), 2)]))
        story.append(t_item)

    if habilidades:
        story.append(Paragraph('HABILIDADES', ESTILOS['sec_lat']))
        for h in habilidades:
            story.append(Paragraph(f'• {h.nombre}', ESTILOS['txt_lat']))

    idiomas_finales = _procesar_idiomas(idiomas)
    if idiomas_finales:
        story.append(Paragraph('IDIOMAS', ESTILOS['sec_lat']))
        for nom, niv in idiomas_finales:
            story.append(Paragraph(f'• {nom}' + (f' ({niv})' if niv else ''), ESTILOS['txt_lat']))

    if intereses:
        story.append(Paragraph('INTERESES', ESTILOS['sec_lat']))
        for it in intereses:
            story.append(Paragraph(f'• {it.nombre}', ESTILOS['txt_lat']))

    story.append(FrameBreak())

    nombre_completo = f"{egresado.nombres} {egresado.apellido_paterno} {egresado.apellido_materno or ''}".strip()
    story.append(Paragraph(nombre_completo, ESTILOS['nombre']))
    story.append(Paragraph(titulo or egresado.titulo_cv or _sugerir_titulo(egresado), ESTILOS['titulo_cv']))
    
    perfil_texto = perfil if perfil is not None else egresado.perfil_profesional
    if perfil_texto:
        story.append(_seccion_con_icono('PERFIL PROFESIONAL'))
        story.append(Paragraph(perfil_texto, ESTILOS['perfil']))

    ancho_tabla = ancho_neto_main - 27

    if empleos:
        story.append(_seccion_con_icono('EXPERIENCIA LABORAL'))
        for emp in empleos:
            empresa = getattr(emp, 'empresa_nombre', None) or (emp.empresa.nombre if hasattr(getattr(emp, 'empresa', None), 'nombre') else str(getattr(emp, 'empresa', '—')))
            inicio = _formatear_fecha(emp.fecha_inicio) if emp.fecha_inicio else ''
            fin = 'Actualidad' if getattr(emp, 'es_actual', False) else (_formatear_fecha(emp.fecha_fin) if emp.fecha_fin else '')
            rango = f"{inicio} – {fin}" if inicio or fin else ""

            t_data = [
                [Paragraph(f"<b>{_formatear_texto(emp.cargo)}</b>", ESTILOS['item_tit']), Paragraph(rango, ESTILOS['fecha_der'])],
                [Paragraph(_formatear_texto(empresa), ESTILOS['item_sub']), '']
            ]
            t = Table(t_data, colWidths=[ancho_tabla - 110, 110])
            t.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ('BOTTOMPADDING', (0,0), (-1,-1), 1),
                ('TOPPADDING', (0,0), (-1,-1), 1),
            ]))
            story.append(t)
            
            for linea in _lineas_a_bullets(emp.funciones):
                story.append(Paragraph(f'• {linea}', ESTILOS['item_bol']))
            story.append(Spacer(1, 5))

    if logros:
        story.append(_seccion_con_icono('FORMACIÓN ACADÉMICA'))
        for l in logros:
            fecha = _formatear_fecha(l.fecha_obtencion) if l.fecha_obtencion else ''
            t_data = [
                [Paragraph(f"<b>{_formatear_texto(l.grado_titulo)}</b>", ESTILOS['item_tit']), Paragraph(fecha, ESTILOS['fecha_der'])],
                [Paragraph(_formatear_texto(l.institucion), ESTILOS['item_sub']), '']
            ]
            t = Table(t_data, colWidths=[ancho_tabla - 110, 110])
            t.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ('BOTTOMPADDING', (0,0), (-1,-1), 1),
                ('TOPPADDING', (0,0), (-1,-1), 1),
            ]))
            story.append(t)
            story.append(Spacer(1, 5))

    if certificados:
        story.append(_seccion_con_icono('CERTIFICACIONES'))
        for c in certificados:
            nom_cert = c.nombre_mostrar() if hasattr(c, 'nombre_mostrar') and callable(getattr(c, 'nombre_mostrar')) else getattr(c, 'nombre', '')
            fecha = _formatear_fecha(c.fecha_emision) if c.fecha_emision else ''
            institucion_c = getattr(c, 'institucion_emisora', '')
            
            t_data = [
                [Paragraph(f"<b>{_formatear_texto(nom_cert)}</b>", ESTILOS['item_tit']), Paragraph(fecha, ESTILOS['fecha_der'])],
                [Paragraph(_formatear_texto(institucion_c), ESTILOS['item_sub']), '']
            ]
            t = Table(t_data, colWidths=[ancho_tabla - 110, 110])
            t.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ('BOTTOMPADDING', (0,0), (-1,-1), 1),
                ('TOPPADDING', (0,0), (-1,-1), 1),
            ]))
            story.append(t)
            story.append(Spacer(1, 5))

    doc.build(story)
    buf.seek(0)
    return buf


# ------------------------------------------------------------
# ESTILOS TIPOGRÁFICOS TIMES NEW ROMAN (CV ALTERNATIVO OPTIMIZADO 1 HOJA)
# ------------------------------------------------------------
ESTILOS_SIMPLE = {
    'nombre':     _estilo('SNombre', fontName='Times-Bold', fontSize=16, leading=24, textColor=colors.black, alignment=TA_CENTER, spaceAfter=2),
    'puesto':     _estilo('SPuesto', fontName='Times-Bold', fontSize=11, leading=16, textColor=colors.black, alignment=TA_CENTER, spaceAfter=3),
    'contacto':   _estilo('SContacto', fontName='Times-Roman', fontSize=9.5, leading=14, textColor=colors.black, alignment=TA_CENTER, spaceAfter=3),
    'seccion':    _estilo('SSeccion', fontName='Times-Bold', fontSize=13, leading=19, textColor=colors.black, spaceBefore=3, spaceAfter=4, keepWithNext=True),
    'texto':      _estilo('STexto', fontName='Times-Roman', fontSize=9.5, leading=14.5, alignment=TA_JUSTIFY),
    'item':       _estilo('SItem', fontName='Times-Bold', fontSize=9.5, leading=14.5, textColor=colors.black, keepWithNext=True),
    'detalle':    _estilo('SDetalle', fontName='Times-Italic', fontSize=9.5, leading=14.5, textColor=colors.black),
    'fecha_der':  _estilo('SFechaDer', fontName='Times-Bold', fontSize=9.5, leading=14.5, textColor=colors.black, alignment=TA_RIGHT),
    'vineta':     _estilo('SVineta', fontName='Times-Roman', fontSize=9.5, leading=14.5, leftIndent=12, bulletIndent=4, spaceAfter=1),
    'idioma_niv': _estilo('SIdiNiv', fontName='Times-Roman', fontSize=9.5, leading=14.5, alignment=TA_LEFT),
}

def _t(texto):
    return _esc(texto or '')

def _rango_empleo(emp):
    inicio = _formatear_fecha(getattr(emp, 'fecha_inicio', None))
    fin = 'Actualidad' if getattr(emp, 'es_actual', False) else _formatear_fecha(getattr(emp, 'fecha_fin', None))
    return f'{inicio} – {fin}' if inicio or fin else ''

def _agregar_separador(story):
    # Espaciado optimizado para mantener apariencia limpia pero ajustar todo a 1 hoja
    story.append(Spacer(1, 5))
    story.append(HRFlowable(width='100%', thickness=0.6, color=colors.black, spaceBefore=2, spaceAfter=6))

# ------------------------------------------------------------
# CV SIMPLE / ALTERNATIVO (COMPACTADO PARA 1 PÁGINA)
# ------------------------------------------------------------
def generar_cv_simple(egresado, puesto, resumen='', empleos=None, logros=None,
                      certificados=None, habilidades=None, idiomas=None):
    empleos, logros, certificados = empleos or [], logros or [], certificados or []
    habilidades, idiomas = habilidades or [], idiomas or []
    S = ESTILOS_SIMPLE

    nombre = _formatear_texto(
        f"{egresado.nombres} {egresado.apellido_paterno} {egresado.apellido_materno or ''}".strip())

    buf = io.BytesIO()
    # Márgenes reducidos ligeramente a 1.4 cm para ganar área útil vertical
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=1.6*cm, rightMargin=1.6*cm,
        topMargin=1.4*cm, bottomMargin=1.4*cm,
        title=f'CV - {nombre}', author=nombre
    )
    story = []

    ancho_util = A4[0] - 3.2*cm

    # Encabezado Centrado
    story.append(Paragraph(_t(nombre), S['nombre']))
    if puesto:
        story.append(Paragraph(_t(puesto), S['puesto']))

    ubicacion = ', '.join(filter(None, [getattr(egresado, 'distrito', None), getattr(egresado, 'provincia', None)]))
    
    linkedin_link = ''
    linkedin_raw = getattr(egresado, 'linkedin', '') or ''
    if linkedin_raw:
        url_lk = linkedin_raw if linkedin_raw.startswith(('http://', 'https://')) else 'https://' + linkedin_raw
        txt_lk = linkedin_raw.replace('https://', '').replace('http://', '').rstrip('/')
        linkedin_link = f'<a href="{url_lk}">{txt_lk}</a>'

    contacto_items = [c for c in [ubicacion, getattr(egresado, 'telefono', None), _correo_contacto(egresado), linkedin_link] if c]
    if contacto_items:
        linea_contacto = '  •  '.join(contacto_items)
        story.append(Paragraph(linea_contacto, S['contacto']))

    _agregar_separador(story)

    # Perfil Profesional
    if resumen and resumen.strip():
        story.append(Paragraph('PERFIL PROFESIONAL', S['seccion']))
        story.append(Paragraph(_t(resumen.strip()).replace('\n', '<br/>'), S['texto']))
        _agregar_separador(story)

    # Experiencia Laboral
    if empleos:
        story.append(Paragraph('EXPERIENCIA LABORAL', S['seccion']))
        for emp in empleos:
            empresa_txt = _formatear_texto(getattr(emp, 'empresa_nombre', '')) or (emp.empresa.nombre if hasattr(getattr(emp, 'empresa', None), 'nombre') else str(getattr(emp, 'empresa', '')))
            rango = _rango_empleo(emp)
            cargo_txt = _formatear_texto(getattr(emp, 'cargo', ''))

            t_data = [
                [Paragraph(f"<b>{_t(cargo_txt)}</b>", S['item']), Paragraph(f"<b>{_t(rango)}</b>", S['fecha_der'])],
                [Paragraph(_t(empresa_txt), S['detalle']), '']
            ]
            t = Table(t_data, colWidths=[ancho_util - 110, 110])
            t.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ]))
            story.append(t)
            
            funciones_texto = getattr(emp, 'funciones', '')
            for linea in _lineas_a_bullets(funciones_texto):
                story.append(Paragraph(_t(linea), S['vineta'], bulletText='•'))
            story.append(Spacer(1, 2))
        
        _agregar_separador(story)

    # Formación Académica
    if logros:
        story.append(Paragraph('FORMACIÓN ACADÉMICA', S['seccion']))
        for l in logros:
            fecha_logro = _formatear_fecha(getattr(l, 'fecha_obtencion', None))
            inst = _formatear_texto(getattr(l, 'institucion', ''))
            titulo_grado = _formatear_texto(getattr(l, 'grado_titulo', ''))

            t_data = [
                [Paragraph(f"<b>{_t(titulo_grado)}</b>", S['item']), Paragraph(f"<b>{_t(fecha_logro)}</b>", S['fecha_der'])],
                [Paragraph(_t(inst), S['detalle']), '']
            ]
            t = Table(t_data, colWidths=[ancho_util - 110, 110])
            t.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ]))
            story.append(t)
            story.append(Spacer(1, 2))

        _agregar_separador(story)

    # Formación Complementaria
    if certificados:
        story.append(Paragraph('FORMACIÓN COMPLEMENTARIA', S['seccion']))
        for c in certificados:
            nom_c = c.nombre_mostrar() if hasattr(c, 'nombre_mostrar') and callable(getattr(c, 'nombre_mostrar')) else getattr(c, 'nombre', '')
            texto = _formatear_texto(nom_c)
            inst_c = getattr(c, 'institucion_emisora', '')
            fecha_cert = _formatear_fecha(getattr(c, 'fecha_emision', None)) if hasattr(c, 'fecha_emision') and c.fecha_emision else ''

            if inst_c:
                texto += f' — {_formatear_texto(inst_c)}'

            t_data = [
                [Paragraph(_t(texto), S['texto']), Paragraph(f"<b>{_t(fecha_cert)}</b>", S['fecha_der'])]
            ]
            t = Table(t_data, colWidths=[ancho_util - 110, 110])
            t.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ]))
            story.append(t)
            story.append(Spacer(1, 1))

        _agregar_separador(story)

    # Habilidades en lista de viñetas
    if habilidades:
        story.append(Paragraph('HABILIDADES', S['seccion']))
        for h in habilidades:
            if hasattr(h, 'nombre') and h.nombre:
                story.append(Paragraph(_t(h.nombre), S['vineta'], bulletText='•'))
        _agregar_separador(story)

    # Idiomas en lista
    idiomas_finales = _procesar_idiomas(idiomas)
    if idiomas_finales:
        story.append(Paragraph('IDIOMAS', S['seccion']))
        tabla_idiomas = []
        for nom, niv in idiomas_finales:
            tabla_idiomas.append([
                Paragraph(f"• {_t(nom)}", S['vineta']),
                Paragraph(_t(niv or ''), S['idioma_niv'])
            ])
        
        t_idiomas = Table(tabla_idiomas, colWidths=[180, ancho_util - 180])
        t_idiomas.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(t_idiomas)

    doc.build(story)
    buf.seek(0)
    return buf