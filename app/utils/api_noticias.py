# app/utils/api_noticias.py
import requests
from datetime import datetime

def obtener_noticias_undac(page=1, per_page=9):
    url = "https://undac.edu.pe/panel/noticias"
    params = {
        'page': page,
        'per_page': per_page,
        'search': '',
        'type': '',
        'range': '',
        'year': ''
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get('data', [])
    except requests.exceptions.RequestException as e:
        print(f"Error en la API: {e}")
        return []

def formatear_fecha(fecha_str):
    if not fecha_str:
        return "Fecha no disponible"
    try:
        fecha = datetime.fromisoformat(fecha_str.replace('Z', '+00:00'))
        return fecha.strftime('%d/%m/%Y')
    except:
        return fecha_str