# app/utils/historial.py
from datetime import datetime, timedelta, timezone

from flask_login import current_user

from app.extensions import db
from app.models import Historial

LIMA = timezone(timedelta(hours=-5))      # Perú no cambia de hora: así no depende del servidor
DIAS_CONSERVACION = 90


def _ahora():
    return datetime.now(LIMA).replace(tzinfo=None)


def registrar(accion, modulo, detalle, guardar=False):
    """
    Anota quién hizo qué. Se suma a la misma transacción de la ruta (si la acción falla, no queda
    rastro). Para consultas, que no guardan nada más, usar guardar=True.
    """
    try:
        db.session.add(Historial(
            fecha=_ahora(),
            id_usuario=current_user.id_usuario if current_user.is_authenticated else None,
            usuario_correo=current_user.correo if current_user.is_authenticated else None,
            rol=current_user.rol if current_user.is_authenticated else None,
            accion=accion, modulo=modulo, detalle=detalle[:300]))
        if guardar:
            db.session.commit()
    except Exception:
        db.session.rollback()      # el historial nunca debe romper la acción principal


def depurar_historial():
    """Borra lo que tenga más de un mes."""
    limite = _ahora() - timedelta(days=DIAS_CONSERVACION)
    Historial.query.filter(Historial.fecha < limite).delete()

    exceso = Historial.query.count() - 5000
    if exceso > 0:
        ids = [i for (i,) in db.session.query(Historial.id_historial)
               .order_by(Historial.fecha.asc()).limit(exceso).all()]
        Historial.query.filter(Historial.id_historial.in_(ids)).delete(synchronize_session=False)

    db.session.commit()