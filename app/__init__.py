# app/__init__.py

import os
from flask import Flask, render_template
from config import Config
from app.extensions import db, login_manager, bcrypt, mail, scheduler

from app.models import Usuario

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Conectar las extensiones a la instancia actual de la aplicación
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    scheduler.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        usuario = db.session.get(Usuario, int(user_id))
        if usuario and usuario.estado == 'activo':
            return usuario
        return None

    # Tareas programadas
    from app.utils.api_empleos import sincronizar_empleos_externos

    @scheduler.task('cron', id='sincronizar_empleos_job', day_of_week='fri', hour=12, minute=42)
    def tarea_sincronizacion_empleos():
        with app.app_context():
            print("⏰ [SCHEDULER] Iniciando sincronización semanal de empleos...")
            res = sincronizar_empleos_externos()
            print(f"📊 Resultado: {res}")

    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        if not scheduler.running:
            scheduler.start()

    # Blueprints
    from app.auth import auth
    from app.egresado import egresado
    from app.public import public
    from app.admin import admin

    app.register_blueprint(auth)
    app.register_blueprint(egresado)
    app.register_blueprint(public)
    app.register_blueprint(admin)

    # Manejo de errores
    @app.errorhandler(404)
    def pagina_no_encontrada(e):
        return render_template('errores/404.html'), 404

    @app.errorhandler(500)
    def error_servidor(e):
        return render_template('errores/500.html'), 500

    @app.template_filter('format_date')
    def format_date(value):
        if not value:
            return 'Fecha no disponible'
        try:
            from datetime import datetime
            fecha = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return fecha.strftime('%d/%m/%Y')
        except Exception:
            return value

    return app