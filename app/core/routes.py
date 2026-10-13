from flask import Blueprint, current_app, render_template, request
from sqlalchemy import select

from app.core.models import AuditLog
from app.extensions import db

bp = Blueprint("core", __name__)


def _audit_query():
    return select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


@bp.route("/")
def dashboard():
    recent = db.session.scalars(_audit_query().limit(8)).all()
    return render_template("core/dashboard.html", recent=recent)


@bp.route("/auditoria")
def audit():
    page = db.paginate(
        _audit_query(),
        page=request.args.get("page", 1, type=int),
        per_page=current_app.config["AUDIT_PAGE_SIZE"],
        error_out=False,
    )
    template = "core/_audit_rows.html" if request.headers.get("HX-Request") else "core/audit.html"
    return render_template(template, page=page)
