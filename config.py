# config.py
import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

class Config:
    # Llave secreta con fallback seguro para desarrollo
    SECRET_KEY = os.getenv('SECRET_KEY')

    if not SECRET_KEY:
        raise RuntimeError('Falta SECRET_KEY en el archivo .env')
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Construcción de la URI con utf8mb4 para soporte completo de acentos y caracteres especiales
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '3306')
    DB_NAME = os.getenv('DB_NAME', 'seguimiento_egresados')

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Límite de carga de archivos (5 MB)
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024    # el PDF se limita a 5 MB en la ruta; el resto es margen
    
    # Ruta absoluta para subida de archivos (evita fallos de rutas relativas)
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'instance', 'uploads')

    # Configuración de correo
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER')

    # Sesiones: se cierran tras N minutos SIN actividad (cada clic la renueva)
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=int(os.getenv('SESION_MINUTOS')))
    SESSION_COOKIE_HTTPONLY = True        # el JavaScript de la página no puede leer la cookie
    SESSION_COOKIE_SECURE = os.getenv('COOKIE_SEGURA') == '1'   # activar en el servidor con HTTPS