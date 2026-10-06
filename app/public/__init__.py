# app/public/__init__.py
from flask import Blueprint

public = Blueprint('public', __name__)

from app.public import routes  # noqa