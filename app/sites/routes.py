import re

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import StringField
from wtforms.validators import DataRequired, Length, Regexp, ValidationError

from app.core.models import utcnow
from app.extensions import db
from app.sites.models import Site

bp = Blueprint("sites", __name__, url_prefix="/sitios")

HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9](-?[a-z0-9])*)(\.[a-z0-9](-?[a-z0-9])*)+$")


class SiteForm(FlaskForm):
    name = StringField("Nombre", validators=[DataRequired(), Length(max=120)])
    key = StringField(
        "Clave",
        description="Identificador único: minúsculas, números y guiones.",
        validators=[
            DataRequired(),
            Length(max=60),
            Regexp(r"^[a-z0-9]+(-[a-z0-9]+)*$", message="Usa minúsculas, números y guiones."),
        ],
    )
    domain = StringField(
        "Dominio previsto",
        description="Se usa en enlaces absolutos y en el sitemap. Ejemplo: losaromos.cl",
        validators=[DataRequired(), Length(max=253)],
    )

    def __init__(self, *args, site=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.site = site

    def validate_key(self, field):
        q = select(Site.id).where(Site.key == field.data)
        if self.site:
            q = q.where(Site.id != self.site.id)
        if db.session.scalar(q):
            raise ValidationError("Ya existe un sitio con esa clave.")

    def validate_domain(self, field):
        field.data = field.data.strip().lower().removeprefix("https://").removeprefix("http://")
        field.data = field.data.rstrip("/")
        if not HOSTNAME.match(field.data):
            raise ValidationError("Escribe un dominio válido, sin ruta. Ejemplo: misitio.cl")


def _go(endpoint):
    """Redirige también las peticiones HTMX (que no siguen un 302 como navegación)."""
    target = url_for(endpoint)
    if request.headers.get("HX-Request"):
        return "", 200, {"HX-Redirect": target}
    return redirect(target)


def _get(site_id):
    return db.session.get(Site, site_id) or abort(404)


@bp.route("/")
def index():
    archived = db.session.scalars(
        select(Site).where(Site.archived_at.is_not(None)).order_by(Site.name)
    ).all()
    return render_template("sites/index.html", archived=archived)


@bp.route("/nuevo", methods=["GET", "POST"])
def new():
    form = SiteForm()
    if form.validate_on_submit():
        site = Site()
        form.populate_obj(site)
        db.session.add(site)
        db.session.commit()
        session["site_id"] = site.id
        flash(f"Sitio «{site.name}» creado y activo.")
        return redirect(url_for("core.dashboard"))
    return render_template("sites/form.html", form=form, site=None)


@bp.route("/<int:site_id>/editar", methods=["GET", "POST"])
def edit(site_id):
    site = _get(site_id)
    form = SiteForm(obj=site, site=site)
    if form.validate_on_submit():
        form.populate_obj(site)
        db.session.commit()
        flash("Cambios guardados.")
        return redirect(url_for("sites.index"))
    return render_template("sites/form.html", form=form, site=site)


@bp.route("/<int:site_id>/archivar", methods=["POST"])
def archive(site_id):
    site = _get(site_id)
    site.archived_at = utcnow()
    db.session.commit()
    flash(f"Sitio «{site.name}» archivado. Puedes restaurarlo desde Sitios.")
    return _go("sites.index")


@bp.route("/<int:site_id>/restaurar", methods=["POST"])
def restore(site_id):
    site = _get(site_id)
    site.archived_at = None
    db.session.commit()
    flash(f"Sitio «{site.name}» restaurado.")
    return redirect(url_for("sites.index"))


@bp.route("/activo", methods=["POST"])
def switch():
    site_id = request.form.get("site_id", type=int)
    if not any(s.id == site_id for s in g.sites):
        abort(400)
    session["site_id"] = site_id
    return _go("core.dashboard")
