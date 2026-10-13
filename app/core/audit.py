"""Registro de auditoría (RF-03).

Las creaciones, ediciones y eliminaciones de modelos Auditable se registran solas al
hacer flush. Las acciones que no son cambios de datos (inicio de sesión, exportación)
se registran con `audit()`.
"""

from flask import has_request_context
from flask_login import current_user
from sqlalchemy import event, insert
from sqlalchemy.orm import Session

from app.core.models import Auditable, AuditLog, utcnow
from app.extensions import db


def _user_id():
    if has_request_context() and current_user.is_authenticated:
        return current_user.id
    return None


def _row(action, obj=None, site_id=None, user_id=None):
    return {
        "site_id": obj.audit_site_id if obj is not None else site_id,
        "user_id": user_id if user_id is not None else _user_id(),
        "action": action,
        "object_type": obj.audit_type if obj is not None else None,
        "object_id": obj.id if obj is not None else None,
        "object_label": obj.audit_label if obj is not None else None,
        "created_at": utcnow(),
    }


def audit(action, obj=None, site_id=None, user_id=None):
    """Agrega una acción explícita a la sesión actual; se guarda con su commit."""
    db.session.add(AuditLog(**_row(action, obj, site_id, user_id)))


@event.listens_for(Session, "after_flush")
def _audit_changes(session, flush_context):
    rows = [_row("crear", o) for o in session.new if isinstance(o, Auditable)]
    rows += [
        _row("editar", o)
        for o in session.dirty
        if isinstance(o, Auditable) and session.is_modified(o, include_collections=False)
    ]
    rows += [_row("eliminar", o) for o in session.deleted if isinstance(o, Auditable)]
    if rows:
        session.connection().execute(insert(AuditLog), rows)
