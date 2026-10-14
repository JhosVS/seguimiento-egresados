# app/auth/forms.py
from datetime import date

from flask_wtf import FlaskForm
from wtforms import (BooleanField, DateField, IntegerField, PasswordField, SelectField, StringField)
from wtforms.validators import (DataRequired, Email, EqualTo, Length, NumberRange, Optional, Regexp, ValidationError)
import re

REQ = 'Este campo es obligatorio.'
_SOLO_LETRAS = r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .-]+$"
MSG_NOMBRE = 'Solo letras, espacios, apóstrofes y guiones.'

def _limpiar(valor):
    return valor.strip() if isinstance(valor, str) else valor

def _minusculas(valor):
    """Quita espacios y pasa a minúsculas (para correos)."""
    return valor.strip().lower() if isinstance(valor, str) else valor

def _limpiar_nombre(valor):
    """Quita espacios sobrantes (inicio, fin y repetidos)."""
    return re.sub(r'\s+', ' ', valor).strip() if isinstance(valor, str) else valor

def _regla_contrasena():
    return [
        DataRequired(message=REQ),
        Length(min=8, max=72, message='Debe tener entre 8 y 72 caracteres.'),
        Regexp(r'^(?=.*[A-Za-z])(?=.*\d).+$', message='Debe incluir letras y números.'),
    ]


class LoginForm(FlaskForm):
    correo = StringField('Correo electrónico', filters=[_minusculas], validators=[DataRequired(message=REQ), Email(message='Correo no válido.'), Length(max=150)])
    contrasena = PasswordField('Contraseña', validators=[DataRequired(message=REQ), Length(max=72)])


class VerificarForm(FlaskForm):
    codigo_universitario = StringField('Código Universitario', filters=[_limpiar], validators=[DataRequired(message=REQ), Regexp(r'^\d{10}$', message='El código debe tener 10 dígitos.')])
    dni = StringField('DNI', filters=[_limpiar], validators=[
        DataRequired(message=REQ), Regexp(r'^\d{8}$', message='El DNI debe tener 8 dígitos.')])


class RecuperarForm(FlaskForm):
    correo = StringField('Correo de tu cuenta', filters=[_limpiar], validators=[DataRequired(message=REQ), Email(message='Correo no válido.')])

class NuevaContrasenaForm(FlaskForm):
    contrasena = PasswordField('Nueva contraseña', validators=_regla_contrasena())
    confirmar = PasswordField('Confirmar contraseña', validators=[DataRequired(message=REQ), EqualTo('contrasena', message='Las contraseñas no coinciden.')])
    def validate_contrasena(self, campo):
        if campo.data and len(campo.data.encode('utf-8')) > 72:
            raise ValidationError('La contraseña es demasiado larga.')


class CambiarContrasenaForm(NuevaContrasenaForm):
    contrasena_actual = PasswordField('Contraseña actual', validators=[DataRequired(message=REQ)])

class RegistroForm(NuevaContrasenaForm):
    # --- Login (Tabla usuarios) ---
    correo = StringField('Correo institucional / de acceso', filters=[_minusculas], validators=[
        DataRequired(message=REQ), Email(message='Correo no válido.'), Length(max=150)
    ])
    confirmar_correo = StringField('Confirmar correo de acceso', filters=[_minusculas], validators=[
        DataRequired(message=REQ), EqualTo('correo', message='Los correos no coinciden.')
    ])

        # --- Identidad (la escribe el egresado, no viene de la API) ---
    nombres = StringField('Nombres', filters=[_limpiar_nombre], validators=[
        DataRequired(message=REQ), Length(min=2, max=100),
        Regexp(_SOLO_LETRAS, message=MSG_NOMBRE)])
    apellido_paterno = StringField('Apellido paterno', filters=[_limpiar_nombre], validators=[
        DataRequired(message=REQ), Length(min=2, max=80),
        Regexp(_SOLO_LETRAS, message=MSG_NOMBRE)])
    apellido_materno = StringField('Apellido materno', filters=[_limpiar_nombre], validators=[
        Optional(), Length(max=80), Regexp(_SOLO_LETRAS, message=MSG_NOMBRE)])

    # --- Datos Personales y Contacto (Tabla egresados) ---
    genero = SelectField('Género', validators=[DataRequired(message='Selecciona tu género.')], choices=[('', 'Selecciona...'), ('M', 'Masculino'), ('F', 'Femenino')])
    fecha_nacimiento = DateField('Fecha de nacimiento', validators=[DataRequired(message=REQ)])
    telefono = StringField('Celular / Teléfono', filters=[_limpiar], validators=[
        DataRequired(message=REQ), Regexp(r'^\+?[\d\s-]{7,20}$', message='Número no válido.')
    ])
    correo_personal = StringField('Correo personal (contacto)', filters=[_limpiar], validators=[
        DataRequired(message=REQ), Email(message='Correo no válido.'), Length(max=150)
    ])
    region = StringField('Región', filters=[_limpiar], validators=[DataRequired(message=REQ), Length(max=100)])
    provincia = StringField('Provincia', filters=[_limpiar], validators=[DataRequired(message=REQ), Length(max=100)])
    distrito = StringField('Distrito', filters=[_limpiar], validators=[DataRequired(message=REQ), Length(max=100)])

    # --- Opcionales (Tabla egresados) ---
    domicilio = StringField('Domicilio', filters=[_limpiar], validators=[Optional(), Length(max=255)])
    anio_ingreso = IntegerField('Año de ingreso', validators=[Optional(), NumberRange(min=1960, max=date.today().year, message='Año no válido.')])
    anio_egreso = IntegerField('Año de egreso', validators=[Optional(), NumberRange(min=1960, max=date.today().year, message='Año no válido.')])

    # --- (Consentimiento) ---
    acepta_tratamiento_datos = BooleanField(
        'Sí, autorizo el tratamiento de mis datos personales',
        validators=[DataRequired(message='Sin tu autorización expresa no podemos crear tu cuenta.')])

    def validate_fecha_nacimiento(self, campo):
        if campo.data and campo.data >= date.today():
            raise ValidationError('La fecha de nacimiento no es válida.')

    def validate_anio_egreso(self, campo):
        if campo.data and self.anio_ingreso.data and campo.data < self.anio_ingreso.data:
            raise ValidationError('No puede ser anterior al año de ingreso.')

    def validate_telefono(self, campo):
        if campo.data and len(re.sub(r'\D', '', campo.data)) < 7:
            raise ValidationError('Número no válido.')