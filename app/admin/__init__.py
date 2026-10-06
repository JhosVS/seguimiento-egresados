# app/admin/__init__.py
from flask import Blueprint
from app.auth.decorators import revisar_personal

admin = Blueprint('admin', __name__)

from app.admin import dashboard
from app.admin import egresados
from app.admin import ofertas
from app.admin import personal
from app.admin import encuestas

@admin.before_request
def proteger_admin():
    return revisar_personal()