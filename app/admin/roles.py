# app/roles.py
# Roles del personal que se pueden USAR hoy. El sistema funciona en una sola escuela, así que
# 'coordinador' (ámbito: facultad) y 'docente_responsable' (ámbito: programa) quedan en la base
# de datos pero no se pueden asignar ni iniciar sesión con ellos.
# Para habilitarlos cuando el sistema se amplíe a más escuelas: agregarlos aquí y volver a
# permitir elegir el rol y su ámbito (facultad o programa) en admin/personal.py.
ROLES_HABILITADOS = ('administrador',)

ROLES_NO_HABILITADOS = {
    'coordinador': 'Coordinador',
    'docente_responsable': 'Docente responsable',
}