# app/__init__.py

import os
from flask import Flask, render_template, request, make_response, redirect, url_for, flash, session, send_from_directory
from config import Config
from app.extensions import db, login_manager, bcrypt, mail, scheduler
from app.utils.historial import depurar_historial
from flask_login import current_user

from app.models import Usuario

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Ruta para servir los archivos subidos desde la carpeta instance/uploads
    @app.route('/uploads/<path:filename>')
    @app.route('/static/uploads/<path:filename>')       # direcciones antiguas de las plantillas
    def uploaded_file(filename):
        return send_from_directory(os.path.join(app.instance_path, 'uploads'), filename)

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

    @app.before_request
    def sesion_permanente():
        # Solo con sesión iniciada: así cada clic renueva el tiempo de inactividad
        if '_user_id' in session:
            session.permanent = True

    @app.before_request
    def cambio_de_contrasena_obligatorio():
        """Una cuenta de personal con contraseña asignada por otra persona debe cambiarla antes de usar el sistema."""
        if (request.endpoint
                and request.endpoint not in ('auth.cambiar_contrasena', 'auth.logout', 'static', 'uploaded_file')
                and current_user.is_authenticated and current_user.es_personal
                and current_user.ultimo_cambio_password is None):
            flash('Por seguridad, es primer inicio de sesión cambia tu contraseña para continuar.', 'warning')
            destino = url_for('auth.cambiar_contrasena')
            if request.headers.get('HX-Request'):
                respuesta = make_response('', 200)
                respuesta.headers['HX-Redirect'] = destino
                return respuesta
            return redirect(destino)

    @login_manager.unauthorized_handler
    def no_autorizado():
        flash('Tu sesión expiró o no has iniciado sesión. Inicia sesión nuevamente.', 'warning')
        # Si la petición viene de HTMX, se le ordena al navegador ir al login completo
        if request.headers.get('HX-Request'):
            respuesta = make_response('', 200)
            respuesta.headers['HX-Redirect'] = url_for('auth.login')
            return respuesta
        return redirect(url_for('auth.login', next=request.full_path.rstrip('?')))

    # Tareas programadas
    from app.utils.api_empleos import sincronizar_empleos_externos

    @scheduler.task('cron', id='sincronizar_empleos_job', day_of_week='sun', hour=1, minute=0)
    def tarea_sincronizacion_empleos():
        with app.app_context():
            print("⏰ [SCHEDULER] Iniciando sincronización semanal de empleos...")
            res = sincronizar_empleos_externos()
            print(f"📊 Resultado: {res}")

    @scheduler.task('cron', id='depurar_historial_job', hour=3, minute=0)
    def tarea_depurar_historial():
        with app.app_context():
            depurar_historial()

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

    @app.errorhandler(413)
    def archivo_muy_grande(e):
        flash('El archivo es demasiado grande (máximo 5 MB).', 'warning')
        destino = request.referrer or url_for('public.index')
        if request.headers.get('HX-Request'):
            respuesta = make_response('', 200)
            respuesta.headers['HX-Redirect'] = destino
            return respuesta
        return redirect(destino)

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