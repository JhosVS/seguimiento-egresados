"""
models.py - Modelos SQLAlchemy del Sistema de Seguimiento de Egresados.

LA FUENTE DE VERDAD ES EL SCRIPT SQL. Estos modelos solo lo describen.
Nunca usar db.create_all(): la base se crea solo con el script SQL.

BLOQUE 1: roles, facultades, programas, currículas, personal, egresados, usuarios.
BLOQUE 2: sectores, empleos, formación, certificados, habilidades, ofertas laborales.
(Falta el bloque 3: encuestas. Se agrega debajo, probando cada bloque.)
"""
from datetime import date

from flask_login import UserMixin

from .extensions import db

# Orden de los grupos en las tablas (mismo criterio que ve el egresado)
ORDEN_TIPO_GRADO = {'doctorado': 0, 'maestria': 1, 'titulado': 2, 'bachiller': 3}
ORDEN_CATEGORIA_CERT = {'especializacion': 0, 'curso': 1, 'capacitacion': 2,
                        'taller': 3, 'idioma': 4, 'otro': 5}

# ============================================================
# 1. ROLES (solo del personal)
# ============================================================
class Rol(db.Model):
    __tablename__ = 'roles'

    id_rol = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)
    descripcion = db.Column(db.String(255))
    ambito = db.Column(db.Enum('global', 'facultad', 'programa'), nullable=False)

    def __repr__(self):
        return f'<Rol {self.nombre}>'


# ============================================================
# 2-4. ESTRUCTURA ACADÉMICA: facultad -> programa -> currícula
# ============================================================
class Facultad(db.Model):
    __tablename__ = 'facultades'

    id_facultad = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False, unique=True)
    codigo = db.Column(db.String(10), unique=True)
    estado = db.Column(db.Enum('activo', 'inactivo'), nullable=False, default='activo')

    programas = db.relationship('ProgramaEstudio', back_populates='facultad')

    def __repr__(self):
        return f'<Facultad {self.nombre}>'


class ProgramaEstudio(db.Model):
    __tablename__ = 'programas_estudio'

    id_programa = db.Column(db.Integer, primary_key=True)
    id_facultad = db.Column(db.Integer, db.ForeignKey('facultades.id_facultad'), nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    codigo = db.Column(db.String(20), unique=True)
    estado = db.Column(db.Enum('activo', 'inactivo'), nullable=False, default='activo')

    facultad = db.relationship('Facultad', back_populates='programas')
    curriculas = db.relationship('Curricula', back_populates='programa')

    def __repr__(self):
        return f'<Programa {self.codigo}>'


class Curricula(db.Model):
    __tablename__ = 'curriculas'

    id_curricula = db.Column(db.Integer, primary_key=True)
    id_programa = db.Column(db.Integer, db.ForeignKey('programas_estudio.id_programa'), nullable=False)
    nombre = db.Column(db.String(50), nullable=False, unique=True)
    anio_inicio = db.Column(db.Integer, nullable=False)   # YEAR de MySQL llega como entero
    anio_fin = db.Column(db.Integer)                      # None = vigente
    estado = db.Column(db.Enum('activo', 'inactivo'), nullable=False, default='activo')

    programa = db.relationship('ProgramaEstudio', back_populates='curriculas')
    egresados = db.relationship('Egresado', back_populates='curricula')

    def __repr__(self):
        return f'<Curricula {self.nombre}>'


# ============================================================
# 5. PERSONAL
# ============================================================
class Personal(db.Model):
    __tablename__ = 'personal'

    id_personal = db.Column(db.Integer, primary_key=True)
    dni = db.Column(db.String(8), unique=True)
    nombres = db.Column(db.String(100), nullable=False)
    apellido_paterno = db.Column(db.String(100), nullable=False)
    apellido_materno = db.Column(db.String(100))
    telefono = db.Column(db.String(30))

    id_rol = db.Column(db.Integer, db.ForeignKey('roles.id_rol'), nullable=False)
    id_facultad = db.Column(db.Integer, db.ForeignKey('facultades.id_facultad'))
    id_programa = db.Column(db.Integer, db.ForeignKey('programas_estudio.id_programa'))

    creado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    rol = db.relationship('Rol')
    facultad = db.relationship('Facultad')
    programa = db.relationship('ProgramaEstudio')
    usuario = db.relationship('Usuario', back_populates='personal', uselist=False)

    @property
    def nombre_completo(self):
        return f'{self.nombres} {self.apellido_paterno} {self.apellido_materno or ""}'.strip()

    def validar_ambito(self):
        """
        La base no puede comparar el rol con la facultad/programa (un CHECK no
        mira otras tablas), asi que lo valida el backend.
        Devuelve un mensaje de error (str) o None si todo esta bien.
        Usarlo ANTES de guardar un personal nuevo o editado.
        """
        rol = db.session.get(Rol, self.id_rol)
        if rol is None:
            return 'El rol no existe.'
        if rol.ambito == 'global' and (self.id_facultad or self.id_programa):
            return 'Un rol global no lleva facultad ni programa.'
        if rol.ambito == 'facultad' and (not self.id_facultad or self.id_programa):
            return 'Este rol requiere una facultad (y ningún programa).'
        if rol.ambito == 'programa' and (not self.id_programa or self.id_facultad):
            return 'Este rol requiere un programa (y ninguna facultad).'
        return None

    def __repr__(self):
        return f'<Personal {self.nombre_completo}>'


# ============================================================
# 6. EGRESADOS
# ============================================================
class Egresado(db.Model):
    __tablename__ = 'egresados'

    id_egresado = db.Column(db.Integer, primary_key=True)

    # Identificación
    codigo_universitario = db.Column(db.String(10), unique=True)
    dni = db.Column(db.String(8), nullable=False, unique=True)
    apellido_paterno = db.Column(db.String(80), nullable=False)
    apellido_materno = db.Column(db.String(80))
    nombres = db.Column(db.String(100), nullable=False)
    genero = db.Column(db.Enum('M', 'F'))
    fecha_nacimiento = db.Column(db.Date)

    # Contacto
    correo_personal = db.Column(db.String(150))
    telefono = db.Column(db.String(20))
    domicilio = db.Column(db.String(255))
    distrito = db.Column(db.String(100))
    provincia = db.Column(db.String(100))
    region = db.Column(db.String(100))
    pais = db.Column(db.String(80), nullable=False, default='Perú')

    # Redes
    linkedin = db.Column(db.String(255))
    facebook = db.Column(db.String(255))
    tiktok = db.Column(db.String(100))
    foto = db.Column(db.String(500))

    # Académico
    id_curricula = db.Column(db.Integer, db.ForeignKey('curriculas.id_curricula'), nullable=False)
    anio_ingreso = db.Column(db.Integer)
    periodo_egreso = db.Column(db.String(10))   # opcional: ej. '25A', '25B', '25D', '25E', '25J', '25N', '25S'
    anio_egreso = db.Column(db.Integer)

    # Perfil
    titulo_cv = db.Column(db.String(150))
    perfil_profesional = db.Column(db.Text)

    # Ley 29733
    acepta_tratamiento_datos = db.Column(db.Boolean, nullable=False, default=False)
    fecha_consentimiento = db.Column(db.DateTime)

    # Control
    creado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    curricula = db.relationship('Curricula', back_populates='egresados')
    usuario = db.relationship('Usuario', back_populates='egresado', uselist=False)

    # Tablas hijas: la base borra en cascada, por eso passive_deletes=True
    empleos = db.relationship('Empleo', back_populates='egresado', cascade='all, delete-orphan',
                              passive_deletes=True, order_by='Empleo.fecha_inicio.desc()')
    formaciones = db.relationship('FormacionAcademica', back_populates='egresado',
                                  cascade='all, delete-orphan', passive_deletes=True,
                                  order_by='FormacionAcademica.fecha_obtencion')
    certificados = db.relationship('Certificado', back_populates='egresado',
                                   cascade='all, delete-orphan', passive_deletes=True)
    habilidades = db.relationship('Habilidad', back_populates='egresado',
                                  cascade='all, delete-orphan', passive_deletes=True)

    @property
    def nombre_completo(self):
        return f'{self.nombres} {self.apellido_paterno} {self.apellido_materno or ""}'.strip()

    @property
    def programa(self):
        return self.curricula.programa

    @property
    def facultad(self):
        return self.curricula.programa.facultad

    def __repr__(self):
        return f'<Egresado {self.dni}>'

    # En app/models.py dentro de class Egresado(db.Model):

    @property
    def tipos_grados(self):
        """Lista de tipos de grados/títulos que posee el egresado."""
        return [f.tipo for f in self.formaciones]

    @property
    def es_bachiller(self):
        return 'bachiller' in self.tipos_grados

    @property
    def es_titulado(self):
        return 'titulado' in self.tipos_grados

    @property
    def tiene_maestria(self):
        return 'maestria' in self.tipos_grados

    @property
    def tiene_doctorado(self):
        return 'doctorado' in self.tipos_grados

    @property
    def nivel_maximo(self):
        if self.tiene_doctorado:
            return 'doctorado'
        elif self.tiene_maestria:
            return 'maestria'
        elif self.es_titulado:
            return 'titulado'
        elif self.es_bachiller:
            return 'bachiller'
        return 'egresado'

    @property
    def empleos_ordenados(self):
        """Actuales primero; luego del más nuevo al más antiguo (por fecha de inicio)."""
        return sorted(self.empleos, key=lambda x: (x.fecha_fin is not None,
                                                   -x.fecha_inicio.toordinal(),
                                                   -x.id_empleo))

    @property
    def formaciones_ordenadas(self):
        """Agrupadas por tipo (nivel más alto primero); dentro de cada tipo, más nuevo primero."""
        return sorted(self.formaciones, key=lambda x: (ORDEN_TIPO_GRADO.get(x.tipo, 99),
                                                       -x.fecha_obtencion.toordinal(),
                                                       -x.id_formacion))

    @property
    def certificados_ordenados(self):
        """Agrupados por categoría; dentro de cada una, más reciente primero (sin fecha al final)."""
        return sorted(self.certificados, key=lambda c: (
            ORDEN_CATEGORIA_CERT.get(c.categoria, 99),
            -(c.fecha_emision.toordinal() if c.fecha_emision else 0),
            -c.id_certificado))

# ============================================================
# 7. USUARIOS (login)
#    Un usuario es de un egresado O de un personal (nunca ambos).
# ============================================================
class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'

    id_usuario = db.Column(db.Integer, primary_key=True)
    correo = db.Column(db.String(150), nullable=False, unique=True)
    contrasena_hash = db.Column(db.String(255), nullable=False)

    id_egresado = db.Column(db.Integer, db.ForeignKey('egresados.id_egresado'), unique=True)
    id_personal = db.Column(db.Integer, db.ForeignKey('personal.id_personal'), unique=True)

    estado = db.Column(db.Enum('activo', 'inactivo'), nullable=False, default='activo')
    ultimo_acceso = db.Column(db.DateTime)

    token_recuperacion_hash = db.Column(db.String(255))
    token_expiracion = db.Column(db.DateTime)
    ultimo_cambio_password = db.Column(db.DateTime)

    creado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    egresado = db.relationship('Egresado', back_populates='usuario')
    personal = db.relationship('Personal', back_populates='usuario')

    # --- Flask-Login ---
    def get_id(self):
        # Flask-Login busca "id" por defecto; nuestra clave se llama id_usuario
        return str(self.id_usuario)

    @property
    def is_active(self):
        # Flask-Login bloquea el acceso si esto es False
        return self.estado == 'activo'

    # --- Ayudas ---
    @property
    def es_egresado(self):
        return self.id_egresado is not None

    @property
    def es_personal(self):
        return self.id_personal is not None

    @property
    def titular(self):
        """El egresado o el personal dueño de la cuenta."""
        return self.egresado if self.es_egresado else self.personal

    @property
    def rol(self):
        """Nombre del rol: 'egresado' o el rol del personal."""
        return 'egresado' if self.es_egresado else self.personal.rol.nombre

    @property
    def nombre_completo(self):
        return self.titular.nombre_completo

    def __repr__(self):
        return f'<Usuario {self.correo}>'


# ============================================================
# 8. SECTORES
# ============================================================
class Sector(db.Model):
    __tablename__ = 'sectores'

    id_sector = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)

    def __repr__(self):
        return f'<Sector {self.nombre}>'


# ============================================================
# 9. EMPLEOS (empleo actual = fecha_fin vacía)
# ============================================================
class Empleo(db.Model):
    __tablename__ = 'empleos'

    id_empleo = db.Column(db.Integer, primary_key=True)
    id_egresado = db.Column(db.Integer, db.ForeignKey('egresados.id_egresado', ondelete='CASCADE'),
                            nullable=False)
    empresa_nombre = db.Column(db.String(200), nullable=False)
    id_sector = db.Column(db.Integer, db.ForeignKey('sectores.id_sector', ondelete='SET NULL'))
    cargo = db.Column(db.String(150), nullable=False)
    tipo_contrato = db.Column(db.String(80))
    funciones = db.Column(db.Text)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date)
    creado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    egresado = db.relationship('Egresado', back_populates='empleos')
    sector = db.relationship('Sector')

    @property
    def es_actual(self):
        return self.fecha_fin is None

    def __repr__(self):
        return f'<Empleo {self.cargo} en {self.empresa_nombre}>'


# ============================================================
# 10. FORMACIÓN ACADÉMICA (grados y títulos)
# ============================================================
class FormacionAcademica(db.Model):
    __tablename__ = 'formacion_academica'

    id_formacion = db.Column(db.Integer, primary_key=True)
    id_egresado = db.Column(db.Integer, db.ForeignKey('egresados.id_egresado', ondelete='CASCADE'),
                            nullable=False)
    tipo = db.Column(db.Enum('bachiller', 'titulado', 'maestria', 'doctorado'), nullable=False)
    grado_titulo = db.Column(db.String(300), nullable=False)
    institucion = db.Column(db.String(200), nullable=False,
                            default='Universidad Nacional Daniel Alcides Carrión')
    fecha_obtencion = db.Column(db.Date, nullable=False)
    fuente = db.Column(db.Enum('SUNEDU', 'MINEDU', 'Otro'), nullable=False, default='SUNEDU')
    creado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    egresado = db.relationship('Egresado', back_populates='formaciones')

    def __repr__(self):
        return f'<Formacion {self.tipo}: {self.grado_titulo}>'


# ============================================================
# 11. CERTIFICADOS Y ESPECIALIZACIONES
# ============================================================
class Certificado(db.Model):
    __tablename__ = 'certificados'

    id_certificado = db.Column(db.Integer, primary_key=True)
    id_egresado = db.Column(db.Integer, db.ForeignKey('egresados.id_egresado', ondelete='CASCADE'),
                            nullable=False)
    nombre = db.Column(db.String(255), nullable=False)          # en pantalla: "Certificado"
    institucion_emisora = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.Enum('curso', 'capacitacion', 'taller', 'idioma', 'otro', 'especializacion'),
                          nullable=False, default='curso')
    nivel_idioma = db.Column(db.Enum('basico', 'intermedio', 'avanzado'))   # solo si categoria = 'idioma'
    fecha_emision = db.Column(db.Date)
    url_credencial = db.Column(db.Text)
    ruta_archivo = db.Column(db.String(500))     # nombre del PDF (carpeta privada instance/certificados/)
    creado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    egresado = db.relationship('Egresado', back_populates='certificados')

    def __repr__(self):
        return f'<Certificado {self.nombre}>'


# ============================================================
# 12. HABILIDADES E INTERESES
# ============================================================
class Habilidad(db.Model):
    __tablename__ = 'habilidades'

    id_habilidad = db.Column(db.Integer, primary_key=True)
    id_egresado = db.Column(db.Integer, db.ForeignKey('egresados.id_egresado', ondelete='CASCADE'),
                            nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.Enum('habilidad', 'interes'), nullable=False, default='habilidad')

    egresado = db.relationship('Egresado', back_populates='habilidades')

    def __repr__(self):
        return f'<Habilidad {self.nombre}>'


# ============================================================
# 13. OFERTAS LABORALES
#     fuente 'automatico' (API de empleos) no lleva id_creado_por;
#     fuente 'manual' sí (lo exige la base con un CHECK).
# ============================================================
class OfertaLaboral(db.Model):
    __tablename__ = 'ofertas_laborales'

    id_oferta = db.Column(db.Integer, primary_key=True)
    id_creado_por = db.Column(db.Integer, db.ForeignKey('personal.id_personal'))
    empresa_nombre = db.Column(db.String(200), nullable=False)
    id_sector = db.Column(db.Integer, db.ForeignKey('sectores.id_sector', ondelete='SET NULL'))
    contacto_telefono = db.Column(db.String(20))
    titulo = db.Column(db.String(255), nullable=False)
    descripcion = db.Column(db.Text)
    requisitos = db.Column(db.Text)
    funciones = db.Column(db.Text)
    modalidad = db.Column(db.String(80))
    tipo_oferta = db.Column(db.String(80))
    jornada = db.Column(db.String(80))
    remuneracion = db.Column(db.String(80))
    ubicacion = db.Column(db.String(200))
    ruta_imagen = db.Column(db.Text)
    url_original = db.Column(db.Text)
    id_externo_job = db.Column(db.String(255), unique=True)
    fuente = db.Column(db.Enum('manual', 'automatico'), nullable=False, default='manual')
    fecha_publicacion = db.Column(db.Date, nullable=False, default=date.today)
    fecha_vencimiento = db.Column(db.Date, nullable=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    actualizado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    creador = db.relationship('Personal')
    sector = db.relationship('Sector')

    @property
    def vigente(self):
        """Activa y todavía no vencida (igual que la vista v_ofertas_vigentes)."""
        return bool(self.activa) and self.fecha_vencimiento >= date.today()

    def __repr__(self):
        return f'<Oferta {self.titulo}>'

# ============================================================
# 14. ENCUESTAS (cuestionarios dinámicos)
# ============================================================
class Encuesta(db.Model):
    __tablename__ = 'encuestas'

    id_encuesta = db.Column(db.Integer, primary_key=True)
    id_creado_por = db.Column(db.Integer, db.ForeignKey('personal.id_personal'), nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    anio = db.Column(db.Integer, nullable=False)          # YEAR de MySQL llega como entero
    estado = db.Column(db.Enum('borrador', 'publicada', 'cerrada'), nullable=False, default='borrador')
    fecha_inicio = db.Column(db.Date)
    fecha_fin = db.Column(db.Date)
    creado_en = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    creador = db.relationship('Personal')
    # La base borra en cascada preguntas y opciones, por eso passive_deletes=True
    preguntas = db.relationship('Pregunta', back_populates='encuesta', cascade='all, delete-orphan',
                                passive_deletes=True, order_by='Pregunta.orden')
    envios = db.relationship('EncuestaEnvio', back_populates='encuesta')

    def __repr__(self):
        return f'<Encuesta {self.nombre}>'


class Pregunta(db.Model):
    __tablename__ = 'preguntas'

    id_pregunta = db.Column(db.Integer, primary_key=True)
    id_encuesta = db.Column(db.Integer, db.ForeignKey('encuestas.id_encuesta', ondelete='CASCADE'),
                            nullable=False)
    seccion = db.Column(db.String(150))
    texto = db.Column(db.Text, nullable=False)
    descripcion = db.Column(db.String(500))
    tipo = db.Column(db.Enum('texto', 'numero', 'si_no', 'opcion_unica', 'opcion_multiple'),
                     nullable=False)
    orden = db.Column(db.Integer, nullable=False)          # único dentro de la encuesta
    obligatoria = db.Column(db.Boolean, nullable=False, default=False)

    encuesta = db.relationship('Encuesta', back_populates='preguntas')
    opciones = db.relationship('Opcion', back_populates='pregunta', cascade='all, delete-orphan',
                               passive_deletes=True, order_by='Opcion.orden')

    def __repr__(self):
        return f'<Pregunta {self.id_pregunta}>'


class Opcion(db.Model):
    __tablename__ = 'opciones'

    id_opcion = db.Column(db.Integer, primary_key=True)
    id_pregunta = db.Column(db.Integer, db.ForeignKey('preguntas.id_pregunta', ondelete='CASCADE'),
                            nullable=False)
    texto = db.Column(db.String(255), nullable=False)
    orden = db.Column(db.Integer, nullable=False)          # único dentro de la pregunta
    requiere_texto = db.Column(db.Boolean, nullable=False, default=False)   # opción tipo "Otro: ..."

    pregunta = db.relationship('Pregunta', back_populates='opciones')

    def __repr__(self):
        return f'<Opcion {self.texto}>'


class EncuestaEnvio(db.Model):
    """Un envío por egresado y encuesta."""
    __tablename__ = 'encuesta_envios'

    id_envio = db.Column(db.Integer, primary_key=True)
    id_encuesta = db.Column(db.Integer, db.ForeignKey('encuestas.id_encuesta'), nullable=False)
    id_egresado = db.Column(db.Integer, db.ForeignKey('egresados.id_egresado'), nullable=False)
    fecha_respuesta = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    encuesta = db.relationship('Encuesta', back_populates='envios')
    egresado = db.relationship('Egresado')
    respuestas = db.relationship('Respuesta', back_populates='envio', cascade='all, delete-orphan',
                                 passive_deletes=True)

    def __repr__(self):
        return f'<Envio encuesta={self.id_encuesta} egresado={self.id_egresado}>'


class Respuesta(db.Model):
    """Una respuesta por pregunta dentro de un envío."""
    __tablename__ = 'respuestas'

    id_respuesta = db.Column(db.Integer, primary_key=True)
    id_envio = db.Column(db.Integer, db.ForeignKey('encuesta_envios.id_envio', ondelete='CASCADE'),
                         nullable=False)
    id_pregunta = db.Column(db.Integer, db.ForeignKey('preguntas.id_pregunta'), nullable=False)
    respuesta_texto = db.Column(db.Text)
    respuesta_numero = db.Column(db.Numeric(10, 2))
    respuesta_si_no = db.Column(db.SmallInteger)           # 1 = Sí, 0 = No (TINYINT, no Boolean)

    envio = db.relationship('EncuestaEnvio', back_populates='respuestas')
    pregunta = db.relationship('Pregunta')
    opciones = db.relationship('RespuestaOpcion', cascade='all, delete-orphan', passive_deletes=True)


class RespuestaOpcion(db.Model):
    """Opciones elegidas: 1 fila en opcion_unica, varias en opcion_multiple."""
    __tablename__ = 'respuesta_opciones'

    id_respuesta = db.Column(db.Integer, db.ForeignKey('respuestas.id_respuesta', ondelete='CASCADE'),
                             primary_key=True)
    id_opcion = db.Column(db.Integer, db.ForeignKey('opciones.id_opcion'), primary_key=True)
    texto_otro = db.Column(db.String(255))

    opcion = db.relationship('Opcion')