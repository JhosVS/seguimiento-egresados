"""
==============================================================================
MÓDULO DE EXTENSIONES (app/extensions.py)
==============================================================================
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_apscheduler import APScheduler

# Instanciación global de las librerías
db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
mail = Mail()
scheduler = APScheduler()

# Configuración por defecto de Flask-Login
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Debes iniciar sesión para acceder a esta página.'
login_message_category = 'warning'