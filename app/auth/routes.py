from flask import Blueprint, current_app, flash, redirect, render_template, session, url_for
from flask_login import login_user, logout_user
from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import EmailField, PasswordField, StringField
from wtforms.validators import DataRequired, Length

from app.auth.models import DUMMY_HASH, User, verify_hash
from app.core.audit import audit
from app.core.models import utcnow
from app.extensions import db, limiter

bp = Blueprint("auth", __name__)


class LoginForm(FlaskForm):
    email = EmailField("Correo", validators=[DataRequired()])
    password = PasswordField("Contraseña", validators=[DataRequired()])


class TotpForm(FlaskForm):
    code = StringField("Código de verificación", validators=[DataRequired(), Length(min=6, max=17)])


def _limit():
    return current_app.config["LOGIN_LIMIT"]


# Solo cuentan los intentos fallidos (401), y ambos pasos comparten el mismo contador.
login_limit = limiter.shared_limit(
    _limit, scope="login", methods=["POST"], deduct_when=lambda r: r.status_code == 401
)


@bp.route("/login", methods=["GET", "POST"])
@login_limit
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = db.session.scalar(select(User).where(User.email == email))
        if user and user.is_active and user.check_password(form.password.data):
            session["pending_user_id"] = user.id
            session["pending_email"] = email
            return redirect(url_for("auth.totp"))
        if not user:
            verify_hash(DUMMY_HASH, form.password.data)
        audit("login_fallido", user_id=user.id if user else None)
        db.session.commit()
        flash("Correo o contraseña incorrectos.", "error")
        return render_template("auth/login.html", form=form), 401
    return render_template("auth/login.html", form=form)


@bp.route("/login/2fa", methods=["GET", "POST"])
@login_limit
def totp():
    user = db.session.get(User, session.get("pending_user_id") or 0)
    if not user or not user.is_active:
        return redirect(url_for("auth.login"))

    form = TotpForm()
    if form.validate_on_submit():
        code = form.code.data.strip().replace(" ", "")
        action = None
        if user.check_totp(code):
            action = "iniciar_sesion"
        elif user.use_recovery_code(code):
            action = "codigo_de_recuperacion"
        if action:
            session.clear()  # evita fijación de sesión
            login_user(user)
            user.last_login_at = utcnow()
            audit(action)
            db.session.commit()
            if action != "iniciar_sesion":
                flash(
                    f"Usaste un código de recuperación. Te quedan {len(user.recovery_codes)}.",
                    "warning",
                )
            return redirect(url_for("core.dashboard"))
        audit("verificacion_fallida", user_id=user.id)
        db.session.commit()
        flash("El código no es válido.", "error")
        return render_template("auth/totp.html", form=form), 401
    return render_template("auth/totp.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    audit("cerrar_sesion")
    db.session.commit()
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))
