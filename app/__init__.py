from zoneinfo import ZoneInfo

from flask import Flask, render_template, request, session

from app.config import Config
from app.extensions import csrf, db, limiter, login_manager, migrate

TZ = ZoneInfo("America/Santiago")

CSP = (
    "default-src 'self'; img-src 'self' data:; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def create_app(config=Config):
    app = Flask(__name__)
    app.config.from_object(config)
    if not app.config["SECRET_KEY"] or not app.config["SQLALCHEMY_DATABASE_URI"]:
        raise RuntimeError("Faltan SECRET_KEY o DATABASE_URL en el entorno (ver .env.example).")

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.session_protection = "strong"

    # Registra los modelos y los eventos de sesión (filtro por sitio y auditoría).
    from app.auth.models import User
    from app.content import models as content_models  # noqa: F401
    from app.core import audit, site_filter  # noqa: F401
    from app.sites.models import Site  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        return user if user and user.is_active else None

    from app.auth.cli import bp as auth_cli_bp
    from app.auth.routes import bp as auth_bp
    from app.content.routes_entries import bp as entries_bp
    from app.content.routes_types import bp as models_bp
    from app.core.routes import bp as core_bp
    from app.sites.routes import bp as sites_bp

    for bp in (auth_bp, auth_cli_bp, core_bp, sites_bp, models_bp, entries_bp):
        app.register_blueprint(bp)

    from app.core.active_site import load_active_site

    app.before_request(load_active_site)

    @app.template_filter("fecha_hora")
    def fecha_hora(value):
        return value.astimezone(TZ).strftime("%d-%m-%Y %H:%M") if value else ""

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.errorhandler(429)
    def too_many_attempts(e):
        from app.core.audit import audit as log

        log("login_bloqueado", user_id=session.get("pending_user_id"))
        db.session.commit()
        template = "auth/totp.html" if request.endpoint == "auth.totp" else "auth/login.html"
        return render_template(template, form=None, blocked=True), 429

    return app
