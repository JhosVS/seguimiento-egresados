# app/auth/decorators.py
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user
from app.extensions import login_manager


def revisar_personal():
    """Deja pasar solo al personal. Devuelve None si puede pasar."""
    if not current_user.is_authenticated:
        return login_manager.unauthorized()      # lo manda al login
    if current_user.es_egresado:
        flash('No tienes permiso para entrar a esa sección.', 'danger')
        return redirect(url_for('egresado.perfil'))


def revisar_egresado():
    """Deja pasar solo a egresados. Devuelve None si puede pasar."""
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
    if not current_user.es_egresado:
        flash('No tienes permiso para entrar a esa sección.', 'danger')
        return redirect(url_for('admin.dashboard'))


def requiere_rol(*roles):
    """Para rutas puntuales. Ejemplo: @requiere_rol('administrador', 'coordinador')"""
    def decorador(f):
        @wraps(f)
        def decorado(*args, **kwargs):
            respuesta = revisar_personal()
            if respuesta:
                return respuesta
            if current_user.rol not in roles:
                flash('No tienes permiso para acceder a esta sección.', 'danger')
                return redirect(url_for('admin.dashboard'))
            return f(*args, **kwargs)
        return decorado
    return decorador