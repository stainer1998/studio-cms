import click
from flask import Blueprint
from sqlalchemy import select

from app.auth.models import User
from app.extensions import db

bp = Blueprint("auth_cli", __name__, cli_group=None)


def _print_codes(codes):
    click.echo("\nCódigos de recuperación (cada uno sirve una vez; guárdalos fuera del servidor):")
    for c in codes:
        click.echo(f"  {c}")


@bp.cli.command("crear-admin")
@click.option("--email", prompt="Correo")
@click.password_option("--password", prompt="Contraseña", confirmation_prompt=True)
def create_admin(email, password):
    """Crea el administrador del Studio con su doble factor."""
    email = email.strip().lower()
    if db.session.scalar(select(User).where(User.email == email)):
        raise click.ClickException("Ya existe un usuario con ese correo.")
    if len(password) < 12:
        raise click.ClickException("La contraseña debe tener al menos 12 caracteres.")

    user = User(email=email)
    user.set_password(password)
    secret = user.new_totp_secret()
    codes = user.new_recovery_codes()
    db.session.add(user)
    db.session.commit()

    click.echo("\nAdministrador creado. Agrega el doble factor en tu app de autenticación:")
    click.echo(f"  Secreto: {secret}")
    click.echo(f"  URI:     {user.totp_uri()}")
    _print_codes(codes)


@bp.cli.command("regenerar-codigos")
@click.option("--email", prompt="Correo")
def regenerate_codes(email):
    """Reemplaza los códigos de recuperación del administrador."""
    user = db.session.scalar(select(User).where(User.email == email.strip().lower()))
    if not user:
        raise click.ClickException("No existe un usuario con ese correo.")
    codes = user.new_recovery_codes()
    db.session.commit()
    _print_codes(codes)
