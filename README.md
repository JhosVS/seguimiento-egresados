# Sistema de Seguimiento de Egresados — UNDAC

Aplicación web para que la Escuela de Ingeniería de Sistemas y Computación de la Universidad Nacional Daniel Alcides Carrión (UNDAC) mantenga el vínculo con sus egresados y conozca su situación laboral y académica. Los datos los registra únicamente cada egresado, previa autorización.

## Funcionalidades

**Egresado**
- Registro verificado con la API de la UNDAC (código universitario y DNI) y autorización de uso de datos.
- Perfil, experiencia laboral, formación profesional y formación complementaria (con PDF opcional). Se registran y editan en la misma tabla, sin cambiar de página.
- CV general en PDF (con diseño) y CV alternativo (solo texto, para postular a una vacante).
- Bolsa de trabajo (ofertas nacionales e internacionales) y encuestas, con aviso de las pendientes.

**Administrador**
- Tablero de control dinámico con filtros (año de egreso e ingreso, situación laboral, currícula y sector) e informe PDF con los filtros aplicados.
- Consulta y exportación de egresados (Excel y PDF).
- Publicación de ofertas, sincronización semanal de empleos externos y gestión de encuestas con resultados y exportación a Excel.
- Gestión de personal e historial de auditoría (conserva un mes).

**Seguridad:** contraseñas cifradas, sesiones que vencen por inactividad, bloqueo temporal tras intentos fallidos, cambio obligatorio de contraseña en cuentas asignadas y PDF de certificados en carpeta privada.

> Por ahora el sistema funciona para una sola escuela. Los roles *coordinador* y *docente responsable* existen en la base de datos, pero no están habilitados.

## Tecnologías

Python · Flask · SQLAlchemy · MySQL 8.4 · Flask-Login · Flask-WTF · Flask-Bcrypt · Flask-Mail · Flask-APScheduler · ReportLab · openpyxl · Bootstrap 5 · HTMX · Chart.js

## Requisitos

- Python 3.10 o superior
- MySQL 8.4
- Un token de la API de la UNDAC y, para las ofertas automáticas, una cuenta en [SerpApi](https://serpapi.com)

## Instalación

```bash
git clone <url-del-repositorio>
cd <carpeta-del-proyecto>

python -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Base de datos.** Ejecuta en MySQL, en este orden, los dos scripts de la carpeta `database/`:

1. `db_seguimiento_egresados_v1.25.sql`: crea las tablas. **Atención:** borra y recrea la base `seguimiento_egresados`; quita la línea `DROP DATABASE` si ya tienes datos.
2. `datos_base.sql`: carga facultades, programas, currículas y sectores. Sin estos datos nadie puede registrarse.

**Configuración.** Crea un archivo `.env` en la raíz (ver la tabla de abajo) y ejecuta:

```bash
flask --app app run --debug
```

La aplicación queda en http://127.0.0.1:5000

## Variables de entorno

```env
SECRET_KEY=una-clave-larga-y-aleatoria
DB_USER=root
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=3306
DB_NAME=seguimiento_egresados
API_UNDAC=token-de-la-api-institucional
SERPAPI_KEY=clave-de-serpapi
MAIL_USERNAME=correo@gmail.com
MAIL_PASSWORD=contraseña-de-aplicacion
MAIL_DEFAULT_SENDER=correo@gmail.com
```

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Obligatoria. Firma las sesiones; si cambia, se cierran todas. |
| `DB_*` | Conexión a MySQL. |
| `API_UNDAC` | Token de la API que verifica código y DNI en el registro. |
| `SERPAPI_KEY` | Ofertas automáticas. El plan gratuito permite 200 consultas al mes; el sistema se detiene en 180. |
| `MAIL_*` | Correo para la recuperación de contraseña (por defecto Gmail con TLS). |
| `SESION_MINUTOS` | Minutos de inactividad antes de cerrar la sesión (por defecto 30). |
| `COOKIE_SEGURA` | `1` cuando el sitio use HTTPS. |
| `MODO_PRUEBAS` | `1` omite la verificación con la API de la UNDAC. **Solo para pruebas.** |

## Primer ingreso

El script crea la cuenta `admin@undac.edu.pe` (la contraseña inicial está indicada en el script). El sistema obliga a cambiarla en el primer inicio de sesión. Después, crea tu propia cuenta de administrador desde **Personal** y desactiva la de prueba.

## Tareas automáticas

- Una vez por semana: sincroniza ofertas laborales de ingeniería de sistemas en Perú y el extranjero. Las ofertas automáticas vencen a los 20 días sin volver a aparecer, y la tabla se limita a 600 ofertas.
- Diariamente: borra del historial lo que tenga más de 30 días.

## Estructura

```
app/
  auth/        inicio de sesión, registro y contraseñas
  egresado/    perfil, empleos, formación, CV y encuestas
  admin/       tablero, egresados, ofertas, encuestas, personal e historial
  public/      inicio, ofertas y noticias
  utils/       historial, CV, sincronización de empleos y utilidades
  templates/   plantillas HTML
instance/      archivos subidos y PDF de certificados (no se sube a Git)
database/      scripts SQL
config.py
```

## Despliegue

- Define las variables de entorno en el servidor y usa `COOKIE_SEGURA=1` con HTTPS.
- No actives `MODO_PRUEBAS`.
- La carpeta `instance/` debe conservarse entre reinicios (disco persistente), porque guarda fotos, afiches y certificados.
- Si el servicio se suspende por inactividad, las tareas automáticas no se ejecutan a su hora.

## Autor

Valladares J — Prácticas pre profesionales, Escuela de Ingeniería de Sistemas y Computación, UNDAC, 2026.