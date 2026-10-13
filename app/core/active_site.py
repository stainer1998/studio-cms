"""Protección de todas las pantallas y carga del sitio activo en cada petición."""

from flask import flash, g, redirect, request, session, url_for
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.sites.models import Site

# Lo único accesible sin sesión completa (contraseña + TOTP).
PUBLIC_ENDPOINTS = {"auth.login", "auth.totp", "static"}
# Lo que se puede usar mientras todavía no existe ningún sitio.
NO_SITE_ENDPOINTS = {"sites.index", "sites.new", "sites.restore", "auth.logout", "core.audit"}


def active_sites():
    return db.session.scalars(
        select(Site).where(Site.archived_at.is_(None)).order_by(Site.name)
    ).all()


def load_active_site():
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))

    sites = active_sites()
    g.sites = sites
    site = next((s for s in sites if s.id == session.get("site_id")), None)
    site = site or (sites[0] if sites else None)
    g.site = site
    g.site_id = site.id if site else None
    session["site_id"] = g.site_id

    if site is None and request.endpoint not in NO_SITE_ENDPOINTS:
        flash("Crea un sitio para empezar.")
        return redirect(url_for("sites.new"))
    return None
