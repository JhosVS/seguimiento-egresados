# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Llave secreta con fallback seguro para desarrollo
    SECRET_KEY = os.getenv('SECRET_KEY')
    FILTRO_ESTRUCTURA_ACTIVO = False   # True = muestra filtros por facultad/programa

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
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    
    # Ruta absoluta para subida de archivos (evita fallos de rutas relativas)
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')

    # Configuración de correo
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER')