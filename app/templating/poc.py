"""Prueba de concepto de GrapesJS con Jinja2 (rama poc/grapesjs-jinja, no se mezcla con main).

El lienzo no imita el resultado: envía el Jinja que exporta cada bloque y muestra lo que
devuelve el mismo motor que usa la vista previa.
"""

from flask import Blueprint, g, jsonify, render_template, request
from markupsafe import escape
from sqlalchemy import select

from app.content.models import ContentType
from app.extensions import db
from app.templating import engine
from app.templating.models import TemplateVersion
from app.templating.routes import EDITOR_CSP, get_template, media_url_for

bp = Blueprint("poc", __name__, url_prefix="/plantillas")


def models_for_editor():
    types = db.session.scalars(select(ContentType).order_by(ContentType.name))
    return [
        {
            "key": ct.key,
            "name": ct.name,
            "fields": [{"key": k, "title": p["title"], "type": p["x-type"]} for k, p in ct.fields],
        }
        for ct in types
    ]


@bp.route("/<int:template_id>/visual-poc")
def editor(template_id):
    template = get_template(template_id)
    g.csp = EDITOR_CSP
    return render_template(
        "templating/visual_poc.html", template=template, models=models_for_editor()
    )


@bp.route("/fragmento", methods=["POST"])
def fragment():
    """Renderiza el Jinja de un bloque con el motor de las plantillas (lienzo del editor)."""
    data = request.get_json(silent=True) or {}
    try:
        html = engine.render(
            data.get("source", ""),
            sample=data.get("datos") == "ejemplo",
            media_url_for=media_url_for,
        )
    except engine.RenderError as e:
        html = f'<p class="cms-error">{escape(e.message)}</p>'
    return html


@bp.route("/<int:template_id>/visual-poc", methods=["POST"])
def save(template_id):
    template = get_template(template_id)
    source = (request.get_json(silent=True) or {}).get("source", "")
    errors = engine.check(source, template.path)
    if errors:
        return jsonify(errors=[e.as_dict() for e in errors]), 422
    template.source, template.mode = source, "visual"
    db.session.add(TemplateVersion(template_id=template.id, source=source))
    db.session.commit()
    return jsonify(errors=[])
