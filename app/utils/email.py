# app/utils/email.py
import os

import requests
from flask import current_app, url_for

URL_BREVO = 'https://api.brevo.com/v3/smtp/email'


def _enviar(destino, asunto, html):
    """Envía un correo por la API de Brevo (HTTPS). Devuelve True si salió bien."""
    try:
        r = requests.post(
            URL_BREVO,
            headers={'api-key': os.environ['BREVO_API_KEY'], 'accept': 'application/json'},
            json={'sender': {'name': os.environ.get('MAIL_REMITENTE_NOMBRE', 'Seguimiento Egresados UNDAC'),
                             'email': os.environ['MAIL_REMITENTE']},
                  'to': [{'email': destino}],
                  'subject': asunto,
                  'htmlContent': html},
            timeout=10)   # sin esto, un fallo del proveedor deja la página colgada otra vez
        r.raise_for_status()
        return True
    except Exception:
        current_app.logger.exception('No se pudo enviar el correo a %s', destino)
        return False


def enviar_correo_recuperacion(correo_destino, token):
    """Envía el correo de restablecimiento de contraseña."""
    enlace = url_for('auth.restablecer_contrasena', token=token, _external=True)
    html = f'''
    <div style="font-family:Segoe UI,sans-serif;max-width:480px;margin:0 auto;">
        <div style="background:#003876;padding:24px;text-align:center;border-radius:12px 12px 0 0;">
            <h2 style="color:#fff;margin:0;font-size:1.2rem;">Sistema de Egresados UNDAC</h2>
            <p style="color:rgba(255,255,255,.75);margin:6px 0 0;font-size:.85rem;">
                Escuela de Sistemas y Computación
            </p>
        </div>
        <div style="background:#fff;padding:28px;border:1px solid #e5e7eb;border-radius:0 0 12px 12px;">
            <p style="color:#374151;">Recibimos una solicitud para restablecer tu contraseña.</p>
            <p style="color:#374151;">Haz clic en el botón para crear una nueva:</p>
            <div style="text-align:center;margin:24px 0;">
                <a href="{enlace}" style="background:#003876;color:#fff;padding:12px 28px;
                   border-radius:8px;text-decoration:none;font-weight:700;">
                    Restablecer contraseña
                </a>
            </div>
            <p style="color:#6b7280;font-size:.82rem;">
                Este enlace expira en <strong>30 minutos</strong>.<br>
                Si no solicitaste esto, ignora este correo.
            </p>
        </div>
    </div>
    '''
    return _enviar(correo_destino, 'Recuperación de contraseña — Egresados UNDAC', html)