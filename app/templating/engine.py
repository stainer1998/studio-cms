"""Motor de plantillas de los sitios (RF-16, RF-17, RNF-04).

Uno solo para el editor, la vista previa y la exportación. Las plantillas viven en la
base de datos y se ejecutan siempre en el sandbox de Jinja2 con un contexto explícito:
solo las funciones y filtros de `functions.py`.
"""

import re
import traceback

from jinja2 import BaseLoader, TemplateNotFound, TemplateSyntaxError, meta
from jinja2.sandbox import ImmutableSandboxedEnvironment, SecurityError
from sqlalchemy import select

from app.core.site_filter import current_site_id
from app.extensions import db
from app.templating import functions
from app.templating.models import Template

INLINE = "<plantilla>"  # nombre de las fuentes sin guardar, para ubicar las líneas con error


class RenderError(Exception):
    def __init__(self, message, line=None):
        super().__init__(message)
        self.message, self.line = message, line

    def as_dict(self):
        return {"message": self.message, "line": self.line}


class DatabaseLoader(BaseLoader):
    """Lee plantillas del sitio activo; el filtro por sitio se aplica solo (RNF-03)."""

    def get_source(self, environment, path):
        row = db.session.execute(
            select(Template.source, Template.updated_at).where(Template.path == path)
        ).first()
        if row is None:
            raise TemplateNotFound(path)
        source, updated_at = row

        def uptodate():
            current = db.session.scalar(select(Template.updated_at).where(Template.path == path))
            return current == updated_at

        return source, path, uptodate


class StudioSandbox(ImmutableSandboxedEnvironment):
    def unsafe_undefined(self, obj, attribute):
        # Jinja devuelve un Undefined que se imprime vacío; aquí el intento falla con un mensaje.
        raise SecurityError(f"access to attribute '{attribute}' is unsafe")


# ponytail: caché por proceso y por sitio; con varios procesos cada uno compila la suya.
_environments = {}


def environment():
    site_id = current_site_id()
    if site_id not in _environments:
        env = StudioSandbox(loader=DatabaseLoader(), autoescape=True)
        env.filters.update(functions.FILTERS)
        _environments[site_id] = env
    return _environments[site_id]


def line_of(exc):
    """Línea de la plantilla donde ocurrió un error de ejecución (Jinja reescribe la traza)."""
    frames = traceback.extract_tb(exc.__traceback__)
    lines = [f.lineno for f in frames if f.filename == INLINE or f.filename.endswith(".html")]
    return lines[-1] if lines else None


# Los errores de sintaxis más comunes, en español; el resto se muestra como lo da Jinja.
SYNTAX_MESSAGES = [
    (
        r"Unexpected end of template\. Jinja was looking for the following tags: (.+?)\. .*",
        r"la plantilla termina sin cerrar un bloque; falta \1.",
    ),
    (
        r"Encountered unknown tag '(\w+)'\. (?:Jinja was looking for the following tags: |"
        r"You probably made a nesting mistake\. Jinja is expecting this tag, but currently "
        r"looking for )(.+?)\. The innermost block that needs to be closed is '(\w+)'\.",
        r"«\1» no va aquí: antes hay que cerrar el bloque «\3» con \2.",
    ),
    (r"Encountered unknown tag '(\w+)'.*", r"etiqueta desconocida «\1»."),
    (r"unexpected end of template, expected '(.+)'\.", r"falta «\1» antes del final."),
    (r"unexpected '(.+)'", r"símbolo inesperado «\1»."),
    (r"expected token '(.+)', got '(.+)'", r"se esperaba «\1» y se encontró «\2»."),
]


def syntax_message(message):
    for pattern, spanish in SYNTAX_MESSAGES:
        if re.fullmatch(pattern, message, re.S):
            spanish = re.sub(pattern, spanish, message, flags=re.S)
            return re.sub(r"'([^']+)'", r"«\1»", spanish).replace("» or «", "» o «")
    return message


def describe(exc):
    if isinstance(exc, TemplateSyntaxError):
        where = f" de «{exc.name}»" if exc.name and exc.name != INLINE else ""
        message = syntax_message(exc.message)
        return RenderError(
            f"Error de sintaxis en la línea {exc.lineno}{where}: {message}", exc.lineno
        )
    if isinstance(exc, TemplateNotFound):
        return RenderError(f"No existe la plantilla «{exc.name}».", line_of(exc))
    if isinstance(exc, SecurityError):
        attr = re.search(r"attribute '([^']+)'", str(exc))
        what = f"«{attr.group(1)}»" if attr else "un atributo interno de Python"
        return RenderError(
            f"La plantilla intentó acceder a {what}, que no está permitido en el sandbox.",
            line_of(exc),
        )
    if isinstance(exc, functions.TemplateDataError):
        return RenderError(str(exc), line_of(exc))
    return RenderError(f"Error al renderizar ({type(exc).__name__}): {exc}", line_of(exc))


def render(source=None, path=None, sample=False, media_url_for=None, **context):
    """Renderiza una fuente sin guardar o una plantilla guardada. Lanza RenderError."""
    env = environment()
    try:
        if source is not None:
            code = env.compile(source, filename=INLINE)
            template = env.template_class.from_code(env, code, env.make_globals(None))
        else:
            template = env.get_template(path)
        return template.render(**context, **functions.build(sample, media_url_for))
    except RenderError:
        raise
    except Exception as e:  # cualquier error de la plantilla se muestra, nunca rompe el Studio
        raise describe(e) from e


def check(source, own_path=None):
    """Errores que impiden guardar: sintaxis y plantillas referenciadas que no existen."""
    env = environment()
    try:
        ast = env.parse(source, filename=INLINE)
    except TemplateSyntaxError as e:
        return [describe(e)]
    errors = []
    for name in meta.find_referenced_templates(ast):
        if name is None or name == own_path:
            continue  # nombres dinámicos no se pueden comprobar sin ejecutar
        if not db.session.scalar(select(Template.id).where(Template.path == name)):
            line = next((i for i, text in enumerate(source.splitlines(), 1) if name in text), None)
            errors.append(RenderError(f"No existe la plantilla «{name}».", line))
    return errors


def references(path):
    """Plantillas que extienden o incluyen `path`."""
    rows = db.session.execute(select(Template.path, Template.source).where(Template.path != path))
    env = environment()
    found = []
    for other, source in rows:
        try:
            names = meta.find_referenced_templates(env.parse(source))
        except TemplateSyntaxError:
            continue
        if path in names:
            found.append(other)
    return found
