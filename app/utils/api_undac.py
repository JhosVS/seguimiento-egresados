# app/utils/api_undac.py
import os
import requests
from flask import current_app

def consultar_api_undac(codigo):
    """
    Consulta los datos del alumno/egresado en la API institucional.
    URL: https://api.undac.edu.pe/tasks/{TOKEN}/{codigo}
    """
    
    token = os.getenv('API_UNDAC')
    if not token:
        current_app.logger.error('API UNDAC: falta la variable API_UNDAC en el .env')
        return None

    if not str(codigo).isdigit():      # el código va dentro de la URL
        return None

    url = f"https://api.undac.edu.pe/tasks/{token}/{codigo}"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            datos = response.json()
            if isinstance(datos, dict) and datos.get('Dni'):
                return datos
        return None
    except (requests.RequestException, ValueError) as e:
        # Solo el tipo de error: el mensaje completo incluye la URL con el token
        current_app.logger.error('API UNDAC no respondió bien (%s)', type(e).__name__)
        return None