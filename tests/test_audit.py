import subprocess

from sqlalchemy import select

from app.core.models import AuditLog
from app.extensions import db
from tests.conftest import create_site, post


def test_crear_y_editar_sitio_queda_en_auditoria(app, auth_client):
    create_site(auth_client, "Panadería Los Aromos", "los-aromos")
    with app.app_context():
        site_id = db.session.scalar(
            select(AuditLog.site_id)
            .where(AuditLog.action == "crear")
            .execution_options(all_sites=True)
        )
    post(
        auth_client,
        f"/sitios/{site_id}/editar",
        {"name": "Panadería Aromos", "key": "los-aromos", "domain": "aromos.cl"},
    )

    with app.app_context():
        q = select(AuditLog).where(AuditLog.object_type == "Sitio").order_by(AuditLog.id)
        rows = db.session.scalars(q.execution_options(all_sites=True)).all()
    assert [(r.action, r.object_label, r.site_id) for r in rows] == [
        ("crear", "Panadería Los Aromos", site_id),
        ("editar", "Panadería Aromos", site_id),
    ]
    assert all(r.user_id and r.created_at for r in rows)

    html = auth_client.get("/auditoria").get_data(as_text=True)
    assert "Creación" in html and "Edición" in html and "Sitio «Panadería Aromos»" in html
    assert "Actividad reciente" in auth_client.get("/").get_data(as_text=True)


def test_auditoria_pagina_con_htmx(app, auth_client):
    app.config["AUDIT_PAGE_SIZE"] = 1
    try:
        for i in range(3):
            create_site(auth_client, f"Sitio {i}", f"sitio-{i}")
        assert "Cargar más" in auth_client.get("/auditoria").get_data(as_text=True)
        r = auth_client.get("/auditoria?page=2", headers={"HX-Request": "true"})
        assert "<html" not in r.get_data(as_text=True)
    finally:
        app.config["AUDIT_PAGE_SIZE"] = 50


def test_migraciones_al_dia_con_los_modelos():
    r = subprocess.run(["flask", "--app", "app", "db", "check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
