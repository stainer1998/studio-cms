"""Aislamiento por sitio aplicado en la capa de consultas (RNF-03).

Toda consulta ORM sobre un modelo SiteScoped se limita al sitio activo (`g.site_id`).
Sin sitio activo no devuelve nada. Para saltarse el filtro hay que pedirlo de forma
explícita con `.execution_options(all_sites=True)`, y solo se usa en CLI y pruebas.
"""

from flask import g, has_app_context
from sqlalchemy import event, false, or_
from sqlalchemy.orm import Session, with_loader_criteria

from app.core.models import AuditLog, SiteScoped


def current_site_id():
    return g.get("site_id") if has_app_context() else None


@event.listens_for(Session, "do_orm_execute")
def _filter_by_site(state):
    if state.is_column_load or state.is_relationship_load:
        return  # heredan el criterio de la consulta que los originó
    if not (state.is_select or state.is_update or state.is_delete):
        return
    if state.execution_options.get("all_sites"):
        return

    site_id = current_site_id()
    if site_id is None:
        scoped = lambda cls: false()  # noqa: E731
        audit = lambda cls: cls.site_id.is_(None)  # noqa: E731
    else:
        scoped = lambda cls: cls.site_id == site_id  # noqa: E731
        audit = lambda cls: or_(cls.site_id == site_id, cls.site_id.is_(None))  # noqa: E731

    state.statement = state.statement.options(
        with_loader_criteria(SiteScoped, scoped, include_aliases=True),
        with_loader_criteria(AuditLog, audit, include_aliases=True),
    )


@event.listens_for(Session, "before_flush")
def _assign_site(session, flush_context, instances):
    for obj in session.new:
        if isinstance(obj, SiteScoped) and obj.site_id is None:
            site_id = current_site_id()
            if site_id is None:
                raise RuntimeError(f"No hay sitio activo para crear {type(obj).__name__}")
            obj.site_id = site_id
