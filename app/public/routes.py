# app/public/routes.py
import json
import re
from datetime import datetime, date

from flask import render_template, redirect, url_for, request
from app.public import public
from app.models import OfertaLaboral, Egresado
from app.extensions import db
from app.utils.api_noticias import obtener_noticias_undac, formatear_fecha

# =======================================
# OFERTAS LABORALES
# =======================================
PAISES_OFERTAS = ['Perú','Lima' ,'España', 'Estados Unidos', 'México', 'Chile', 'Colombia' ]


def _url_segura(url):
    """Solo se permiten enlaces http/https (evita enlaces tipo javascript:)."""
    return url if url and url.startswith(('http://', 'https://')) else None


@public.route('/ofertas-laborales')
def ofertas():
    # Desactivar ofertas con fecha de vencimiento superada
    OfertaLaboral.query.filter(
        OfertaLaboral.fecha_vencimiento < date.today(),
        OfertaLaboral.activa == 1
    ).update({'activa': 0})
    db.session.commit()

    base = OfertaLaboral.query.filter_by(activa=1)
    total_activas = base.count()

    # Cantidad de ofertas por país, para los botones del filtro
    paises = [
        {'nombre': p,
         'total': base.filter(OfertaLaboral.ubicacion.ilike(f'%{p}')).count()}
        for p in PAISES_OFERTAS
    ]

    # País elegido (?pais=España). Si no es uno válido, se ignora.
    pais_activo = request.args.get('pais')
    if pais_activo not in PAISES_OFERTAS:
        pais_activo = None

    consulta = base
    if pais_activo:
        consulta = consulta.filter(OfertaLaboral.ubicacion.ilike(f'%{pais_activo}'))
    lista = consulta.order_by(OfertaLaboral.fecha_publicacion.desc()).all()

    def obtener_url_imagen(ruta):
        if not ruta:
            return None
        if ruta.startswith('http://') or ruta.startswith('https://'):
            return ruta
        return url_for('static', filename=ruta)

    # Ahora es una lista normal; la plantilla la convierte con |tojson
    ofertas_json = [{
        'id': o.id_oferta,
        'titulo': o.titulo,
        'empresa': o.empresa_nombre,
        'telefono': o.contacto_telefono,
        'tipo_oferta': o.tipo_oferta,
        'jornada': o.jornada,
        'remuneracion': o.remuneracion,
        'modalidad': o.modalidad,
        'ubicacion': o.ubicacion,
        'descripcion': o.descripcion,
        'funciones': o.funciones,
        'requisitos': o.requisitos,
        'fuente': o.fuente,
        'ruta_imagen': obtener_url_imagen(o.ruta_imagen),
        'url_original': _url_segura(o.url_original),
        'fecha_publicacion': o.fecha_publicacion.strftime('%d/%m/%Y') if o.fecha_publicacion else None,
        'fecha_vencimiento': o.fecha_vencimiento.strftime('%d/%m/%Y') if o.fecha_vencimiento else None,
    } for o in lista]

    portales = [
        {
            'titulo': 'Computrabajo',
            'subtitulo': 'Portal líder en Perú',
            'descripcion': 'Miles de ofertas diarias. Filtra por "Ingeniería de sistemas" en Pasco o Lima.',
            'url': 'https://pe.computrabajo.com/trabajo-de-sistemas-en-pasco',
            'color': '#0073b1',
            'icono': 'bi-briefcase-fill'
        },
        {
            'titulo': 'Indeed Perú',
            'subtitulo': 'Motor de búsqueda global',
            'descripcion': 'Agrega ofertas de múltiples fuentes. Busca "sistemas" en Pasco.',
            'url': 'https://pe.indeed.com/jobs?q=sistemas&l=Pasco',
            'color': '#2164f3',
            'icono': 'bi-search'
        },
        {
            'titulo': 'Bumeran',
            'subtitulo': 'Portal peruano',
            'descripcion': 'Popular entre empresas peruanas. Filtra por tecnología e informática.',
            'url': 'https://www.bumeran.com.pe/empleos-busqueda-informatica-sistemas.html',
            'color': '#e8a400',
            'icono': 'bi-person-workspace'
        },
        {
            'titulo': 'LinkedIn',
            'subtitulo': 'Red profesional global',
            'descripcion': 'Ideal para conectar con empresas. Busca "Ingeniero de sistemas" en Perú.',
            'url': 'https://www.linkedin.com/jobs/search/?keywords=ingeniero%20sistemas&location=Per%C3%BA',
            'color': '#0a66c2',
            'icono': 'bi-linkedin'
        },
        {
            'titulo': 'Universia',
            'subtitulo': 'Bolsa universitaria',
            'descripcion': 'Ofertas orientadas a universitarios y recién egresados de carreras técnicas.',
            'url': 'https://jobboard.universia.net/unheval_fiis?dateFrom=all&page=1',
            'color': '#00875a',
            'icono': 'bi-mortarboard-fill'
        },
        {
            'titulo': 'Conocatorias de Trabajo',
            'subtitulo': 'Portal peruano',
            'descripcion': 'Ofertas de empleo y practicas del estado.',
            'url': 'https://www.convocatoriasdetrabajo.com',
            'color': '#c53030',
            'icono': 'bi-newspaper'
        }
    ]

    return render_template('public/ofertas.html',
        ofertas=lista,
        ofertas_json=ofertas_json,
        portales=portales,
        paises=paises,
        pais_activo=pais_activo,
        total_activas=total_activas,
        anio=date.today().year
    )

# =======================================
# ALIAS PARA OFERTAS (URL más amigable)
# =======================================
@public.route('/ofertas')
def ofertas_redirect():
    return redirect(url_for('public.ofertas'))

# =======================================
# PAGINA DE INICIO
# =======================================
@public.route('/')
def index():
    total_egresados = Egresado.query.count()
    ofertas_count = OfertaLaboral.query.filter_by(activa=1).count()  # <--- Corregido a OfertaLaboral
    return render_template('public/index.html',
        total_egresados=total_egresados,
        ofertas=ofertas_count,
        anio=date.today().year
    )

# =======================================
# PAGINA DE QUIENES SOMOS
# =======================================
@public.route('/quienes-somos')
def quienes_somos():
    return render_template('public/quienes_somos.html', 
        anio=date.today().year
    )

# =======================================
# PAGINA DE NOTICIAS
# =======================================
@public.route('/noticias')
def noticias():
    pagina = request.args.get('page', 1, type=int)
    if pagina < 1:
        pagina = 1
    
    noticias_raw = obtener_noticias_undac(pagina)
    
    noticias_procesadas = []
    for n in noticias_raw:
        descripcion_raw = n.get('description', '')
        if descripcion_raw:
            descripcion_limpia = re.sub(r'<[^>]+>', '', descripcion_raw)
            descripcion_limpia = descripcion_limpia.replace('&Oacute;', 'Ó')
            descripcion_limpia = descripcion_limpia.replace('&oacute;', 'ó')
            descripcion_limpia = descripcion_limpia.replace('&Aacute;', 'Á')
            descripcion_limpia = descripcion_limpia.replace('&aacute;', 'á')
            descripcion_limpia = descripcion_limpia.replace('&Eacute;', 'É')
            descripcion_limpia = descripcion_limpia.replace('&eacute;', 'é')
            descripcion_limpia = descripcion_limpia.replace('&Iacute;', 'Í')
            descripcion_limpia = descripcion_limpia.replace('&iacute;', 'í')
            descripcion_limpia = descripcion_limpia.replace('&Uacute;', 'Ú')
            descripcion_limpia = descripcion_limpia.replace('&uacute;', 'ú')
            descripcion_limpia = descripcion_limpia.replace('&Ntilde;', 'Ñ')
            descripcion_limpia = descripcion_limpia.replace('&ntilde;', 'ñ')
        else:
            descripcion_limpia = ''
        
        noticias_procesadas.append({
            'titulo': n.get('title', 'Sin título'),
            'fecha': formatear_fecha(n.get('created_at')),
            'enlace': f"https://undac.edu.pe/noticias/{n.get('slug', n.get('id'))}",
            'imagen': n.get('image_url', '') or n.get('image_path', ''),
            'categoria': n.get('type', 'Noticia'),
            'resumen': descripcion_limpia[:180]
        })
    
    total_paginas = 2 if len(noticias_raw) == 9 else 1
    
    return render_template('public/noticias.html',
        noticias=noticias_procesadas,
        total=len(noticias_procesadas),
        pagina_actual=pagina,
        total_paginas=total_paginas,
        fecha_actualizacion=datetime.now().strftime('%d/%m/%Y %H:%M'),
        anio=date.today().year
    )