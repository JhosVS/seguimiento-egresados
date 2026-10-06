# app/egresado/__init__.py
from flask import Blueprint
from app.auth.decorators import revisar_egresado

egresado = Blueprint('egresado', __name__)

from app.egresado import routes

@egresado.before_request
def proteger_egresado():
    return revisar_egresado()