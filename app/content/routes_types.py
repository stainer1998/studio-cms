"""Constructor de modelos (RF-05 a RF-08)."""

import json
import re
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from sqlalchemy import func, select, update
from sqlalchemy.orm.attributes import flag_modified
from wtforms import StringField
from wtforms.validators import DataRequired, Length, Regexp, ValidationError

from app.content import fields as F
from app.content.models import ContentType, Entry
from app.extensions import db

bp = Blueprint("models", __name__, url_prefix="/modelos")


class ContentTypeForm(FlaskForm):
    name = StringField("Nombre visible", validators=[DataRequired(), Length(max=120)])
    key = StringField(
        "Nombre interno",
        description="Se usa en las plantillas: entradas('producto'). No se puede cambiar.",
        validators=[
            DataRequired(),
            Length(max=60),
            Regexp(
                F.KEY_PATTERN, message="Usa minúsculas, números y guiones bajos; empieza con letra."
            ),
        ],
    )

    def validate_key(self, field):
        if db.session.scalar(select(ContentType.id).where(ContentType.key == field.data)):
            raise ValidationError("Ya existe un modelo con ese nombre interno en este sitio.")


def get_type(type_id):
    return db.one_or_404(select(ContentType).where(ContentType.id == type_id))


def all_types():
    return db.session.scalars(select(ContentType).order_by(ContentType.name)).all()


def usage_count(ct, key):
    """Entradas del modelo que tienen un valor guardado en el campo."""
    q = select(func.count(Entry.id)).where(Entry.content_type_id == ct.id, Entry.data.has_key(key))
    return db.session.scalar(q)


def render_model(ct, editing=None, field_form=None, errors=None, status=200):
    """Página del modelo, o solo su cuerpo si la petición viene de HTMX."""
    if field_form is None and "type" in request.args:
        # El panel se vuelve a pedir al cambiar el tipo: se conserva lo escrito.
        field_form = request.args.to_dict() | {"required": "required" in request.args}
        field_form["key"] = editing or field_form.get("key", "")
    elif field_form is None and editing:
        prop = ct.schema["properties"][editing]
        field_form = {
            "label": prop["title"],
            "key": editing,
            "type": prop["x-type"],
            "required": editing in ct.schema["required"],
            "help": prop.get("description", ""),
            "minimum": prop.get("minimum", prop.get("minLength", "")),
            "maximum": prop.get("maximum", prop.get("maxLength", "")),
            "default": prop.get("default", ""),
            "ref": prop.get("x-ref", ""),
            "slug_source": ct.slug_source or "",
        }
    ctx = {
        "ct": ct,
        "types": all_types(),
        "editing": editing,
        "f": field_form or {"type": "text"},
        "errors": errors or {},
        "type_locked": bool(editing and usage_count(ct, editing)),
        "schema_json": json.dumps(ct.schema, ensure_ascii=False, indent=2),
        "entry_count": db.session.scalar(
            select(func.count(Entry.id)).where(Entry.content_type_id == ct.id)
        ),
        "TYPES": F.TYPES,
    }
    template = (
        "content/_model_body.html" if request.headers.get("HX-Request") else "content/model.html"
    )
    return render_template(template, **ctx), status


@bp.route("/")
def index():
    types = all_types()
    if types:
        return redirect(url_for("models.show", type_id=types[0].id))
    return render_template("content/models_empty.html")


@bp.route("/nuevo", methods=["GET", "POST"])
def new():
    form = ContentTypeForm()
    if form.validate_on_submit():
        ct = ContentType(name=form.name.data.strip(), key=form.key.data)
        db.session.add(ct)
        db.session.commit()
        flash(f"Modelo «{ct.name}» creado. Agrega sus campos.")
        return redirect(url_for("models.show", type_id=ct.id))
    return render_template("content/model_new.html", form=form, types=all_types())


@bp.route("/<int:type_id>")
def show(type_id):
    ct = get_type(type_id)
    return render_model(ct, editing=request.args.get("campo"))


@bp.route("/<int:type_id>", methods=["POST"])
def rename(type_id):
    ct = get_type(type_id)
    name = request.form.get("name", "").strip()
    if name and len(name) <= 120:
        ct.name = name
        db.session.commit()
        flash("Cambios guardados.")
    return redirect(url_for("models.show", type_id=ct.id))


def _number(raw, label, errors, key, integer=False):
    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        errors[key] = f"{label}: escribe un número."
        return None
    if integer:
        if not value.is_integer() or value < 0:
            errors[key] = f"{label}: escribe un número entero mayor o igual a 0."
            return None
        return int(value)
    return int(value) if value.is_integer() else value


def parse_field_form(ct, form, editing=None):
    """Lee el panel «Editar campo».

    Devuelve (clave, propiedad, requerido, origen del slug, errores, valores escritos).
    """
    errors = {}
    f = {
        k: form.get(k, "")
        for k in (
            "label",
            "key",
            "type",
            "help",
            "minimum",
            "maximum",
            "default",
            "ref",
            "slug_source",
        )
    }
    f["required"] = "required" in form

    key = editing or f["key"].strip()
    old = ct.schema["properties"].get(editing, {})
    ftype = f["type"] if not (editing and usage_count(ct, editing)) else old["x-type"]
    f["key"], f["type"] = key, ftype

    label = f["label"].strip()
    if not label:
        errors["label"] = "Escribe la etiqueta del campo."
    elif len(label) > 120:
        errors["label"] = "Máximo 120 caracteres."
    if not editing:
        if not re.match(F.KEY_PATTERN, key) or len(key) > 60:
            errors["key"] = "Usa minúsculas, números y guiones bajos; empieza con letra."
        elif key in ct.schema["properties"]:
            errors["key"] = "Ya existe un campo con ese nombre interno."
    if ftype not in F.TYPES:
        errors["type"] = "Elige un tipo."
        return key, None, False, None, errors, f

    minimum = maximum = default = ref = slug_source = None
    if ftype in {"text", "number"}:
        integer = ftype == "text"
        minimum = _number(f["minimum"], "Mínimo", errors, "minimum", integer)
        maximum = _number(f["maximum"], "Máximo", errors, "maximum", integer)
        if minimum is not None and maximum is not None and minimum > maximum:
            errors["maximum"] = "El máximo debe ser mayor o igual al mínimo."

    raw_default = f["default"].strip()
    if ftype == "number":
        default = _number(raw_default, "Valor por defecto", errors, "default")
    elif ftype == "text" and raw_default:
        default = raw_default
    elif ftype == "bool":
        default = "default" in form
    elif ftype == "date" and raw_default:
        try:
            default = date.fromisoformat(raw_default).isoformat()
        except ValueError:
            errors["default"] = "Escribe una fecha válida."

    if ftype == "slug":
        other_slug = ct.slug_field
        if other_slug and other_slug != key:
            errors["type"] = "El modelo ya tiene un campo slug."
        text_fields = [k for k, p in ct.fields if p["x-type"] == "text"]
        slug_source = f["slug_source"]
        if slug_source not in text_fields:
            errors["slug_source"] = "Elige el campo de texto desde el que se genera el slug."
    if ftype == "relation":
        ref = int(f["ref"]) if f["ref"].isdigit() else None
        if ref is None or not db.session.scalar(
            select(ContentType.id).where(ContentType.id == ref)
        ):
            errors["ref"] = "Elige el modelo relacionado."

    # ponytail: una imagen no puede ser requerida hasta que exista el selector de Medios (H3).
    required = f["required"] and ftype != "image"
    prop = F.build_property(ftype, label, f["help"].strip(), minimum, maximum, default, ref)
    return key, prop, required, slug_source, errors, f


@bp.route("/<int:type_id>/campos", methods=["POST"])
@bp.route("/<int:type_id>/campos/<key>", methods=["POST"])
def save_field(type_id, key=None):
    ct = get_type(type_id)
    if key and key not in ct.schema["properties"]:
        return redirect(url_for("models.show", type_id=ct.id))
    editing = key
    key, prop, required, slug_source, errors, f = parse_field_form(ct, request.form, editing)
    if errors:
        return render_model(ct, editing=editing, field_form=f, errors=errors, status=422)

    ct.schema = F.with_field(ct.schema, key, prop, required)
    if prop["x-type"] == "slug":
        ct.slug_source = slug_source
    elif ct.slug_source == key:
        ct.slug_source = None
    db.session.commit()
    return _back(ct, key, "Campo guardado.")


@bp.route("/<int:type_id>/campos/<key>/mover", methods=["POST"])
def move_field(type_id, key):
    ct = get_type(type_id)
    if key in ct.schema["properties"]:
        ct.schema = F.moved_field(ct.schema, key, -1 if request.form.get("dir") == "arriba" else 1)
        # Solo cambia el orden: para SQLAlchemy los dicts son iguales y no guardaría nada.
        flag_modified(ct, "schema")
        db.session.commit()
    return _back(ct, key)


@bp.route("/<int:type_id>/campos/<key>/eliminar", methods=["GET", "POST"])
def delete_field(type_id, key):
    ct = get_type(type_id)
    if key not in ct.schema["properties"]:
        return redirect(url_for("models.show", type_id=ct.id))
    count = usage_count(ct, key)
    if request.method == "GET":
        page = (
            "content/_delete_field.html"
            if request.headers.get("HX-Request")
            else "content/delete_field.html"
        )
        return render_template(page, ct=ct, key=key, count=count)

    ct.schema = F.without_field(ct.schema, key)
    if ct.slug_source == key:
        ct.slug_source = None
    if count:
        db.session.execute(
            update(Entry)
            .where(Entry.content_type_id == ct.id, Entry.data.has_key(key))
            .values(data=Entry.data.op("-")(key))
        )
    db.session.commit()
    return _back(ct, None, f"Campo «{key}» eliminado.")


def _back(ct, key, message=None):
    if message:
        flash(message)
    if request.headers.get("HX-Request"):
        return render_model(ct, editing=key)
    return redirect(url_for("models.show", type_id=ct.id, campo=key))
