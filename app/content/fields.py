"""Campos de los modelos: esquema JSON, lectura del formulario de una entrada y validación.

El esquema de cada modelo (content_types.schema) es la única fuente de verdad. Cada campo
es una propiedad de JSON Schema con `title` (etiqueta), `description` (ayuda), `default`
y `x-type` (tipo del Studio); las relaciones agregan `x-ref` (id del modelo relacionado).
"""

import re
import unicodedata

import nh3
from jsonschema import Draft202012Validator, FormatChecker

TYPES = {
    "text": "Texto",
    "rich": "Texto enriquecido",
    "number": "Número",
    "date": "Fecha",
    "bool": "Booleano",
    "image": "Imagen",
    "slug": "Slug",
    "relation": "Relación",
}
SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
KEY_PATTERN = r"^[a-z][a-z0-9_]*$"

RICH_TAGS = {
    "p",
    "h2",
    "h3",
    "h4",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "a",
    "img",
    "br",
    "blockquote",
}
RICH_ATTRIBUTES = {"a": {"href", "title"}, "img": {"src", "alt"}}


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:200]


def sanitize_html(html):
    """Lista blanca del texto enriquecido (RNF-05). Se aplica antes de guardar."""
    return nh3.clean(
        html,
        tags=RICH_TAGS,
        attributes=RICH_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    ).strip()


def build_property(
    ftype, label, help_text=None, minimum=None, maximum=None, default=None, ref=None
):
    prop = {"title": label, "x-type": ftype}
    if help_text:
        prop["description"] = help_text
    match ftype:
        case "text":
            prop["type"] = "string"
            if minimum is not None:
                prop["minLength"] = int(minimum)
            if maximum is not None:
                prop["maxLength"] = int(maximum)
        case "rich":
            prop |= {"type": "string", "format": "html"}
        case "number":
            prop["type"] = "number"
            if minimum is not None:
                prop["minimum"] = minimum
            if maximum is not None:
                prop["maximum"] = maximum
        case "date":
            prop |= {"type": "string", "format": "date"}
        case "bool":
            prop["type"] = "boolean"
        case "image":
            prop["type"] = "integer"  # id del medio (H3)
        case "slug":
            prop |= {"type": "string", "pattern": SLUG_PATTERN}
        case "relation":
            prop |= {"type": "integer", "x-ref": ref}
    if default is not None and ftype in {"text", "number", "date", "bool"}:
        prop["default"] = default
    return prop


def with_field(schema, key, prop, required, after=None):
    """Copia del esquema con el campo agregado o reemplazado (conserva su posición)."""
    props = dict(schema["properties"])
    props[key] = prop
    req = [k for k in schema["required"] if k != key] + ([key] if required else [])
    return {**schema, "required": req, "properties": props}


def without_field(schema, key):
    props = {k: v for k, v in schema["properties"].items() if k != key}
    return {**schema, "required": [k for k in schema["required"] if k != key], "properties": props}


def moved_field(schema, key, step):
    keys = list(schema["properties"])
    i = keys.index(key)
    j = max(0, min(len(keys) - 1, i + step))
    keys.insert(j, keys.pop(i))
    return {**schema, "properties": {k: schema["properties"][k] for k in keys}}


# --- Formulario de una entrada ---------------------------------------------------------


def parse_form(content_type, form, current=None):
    """Convierte el formulario en `data` tipado. Devuelve (data, errores por campo)."""
    data, errors = {}, {}
    current = current or {}
    for key, prop in content_type.fields:
        ftype = prop["x-type"]
        raw = (form.get(key) or "").strip()
        if ftype == "bool":
            data[key] = key in form
        elif ftype == "image":
            if key in current:  # el selector llega con la biblioteca de medios (H3)
                data[key] = current[key]
        elif ftype == "rich":
            html = sanitize_html(raw)
            if re.sub(r"<[^>]+>|&nbsp;|\s", "", html) or "<img" in html:
                data[key] = html
        elif ftype in {"number", "relation"}:
            if raw:
                try:
                    value = float(raw.replace(",", "."))
                    data[key] = int(value) if ftype == "relation" or value.is_integer() else value
                except ValueError:
                    errors[key] = "Escribe un número."
        elif raw:
            data[key] = raw

    slug_key = content_type.slug_field
    source = content_type.slug_source
    if slug_key and not data.get(slug_key) and source and data.get(source):
        data[slug_key] = slugify(str(data[source]))
    return data, errors


MESSAGES = {
    "required": lambda e: "Este campo es obligatorio.",
    "minLength": lambda e: f"Debe tener al menos {e.validator_value} caracteres.",
    "maxLength": lambda e: f"Debe tener como máximo {e.validator_value} caracteres.",
    "minimum": lambda e: f"Debe ser mayor o igual a {e.validator_value:g}.",
    "maximum": lambda e: f"Debe ser menor o igual a {e.validator_value:g}.",
    "pattern": lambda e: "Usa solo minúsculas, números y guiones.",
    "format": lambda e: (
        "Escribe una fecha válida." if e.validator_value == "date" else "Valor no válido."
    ),
}


def validate(schema, data):
    """Valida contra el esquema del modelo y devuelve los errores por campo, en español."""
    errors = {}
    for e in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data):
        key = (
            e.message.split("'")[1]
            if e.validator == "required"
            else (e.path[0] if e.path else None)
        )
        if key is not None:
            errors.setdefault(key, MESSAGES.get(e.validator, lambda e: "Valor no válido.")(e))
    return errors
