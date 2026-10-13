"""Aislamiento por sitio (RNF-03): leer datos de otro sitio debe fallar."""

import pytest
from flask import g
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import AuditLog, SiteScoped
from app.extensions import db
from app.sites.models import Site


class Note(SiteScoped, db.Model):
    """Tabla de contenido mínima, solo para probar el filtro genérico."""

    __tablename__ = "test_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str]


@pytest.fixture
def two_sites(app):
    with app.app_context():
        a, b = Site(name="A", key="a", domain="a.cl"), Site(name="B", key="b", domain="b.cl")
        db.session.add_all([a, b])
        db.session.commit()
        return a.id, b.id


def test_consultas_ven_solo_el_sitio_activo(app, two_sites):
    a, b = two_sites
    with app.app_context():
        g.site_id = a
        db.session.add(Note(text="de A"))  # site_id se asigna solo
        db.session.commit()
        g.site_id = b
        db.session.add(Note(text="de B"))
        db.session.commit()

        assert [n.text for n in db.session.scalars(select(Note))] == ["de B"]
        g.site_id = a
        assert [n.text for n in db.session.scalars(select(Note))] == ["de A"]
        # Ni pidiendo la fila por id de otro sitio.
        other = db.session.scalar(select(Note.id).where(Note.text == "de A"))
        g.site_id = b
        db.session.expunge_all()
        assert db.session.scalar(select(Note).where(Note.id == other)) is None


def test_sin_sitio_activo_no_devuelve_nada(app, two_sites):
    a, _ = two_sites
    with app.app_context():
        g.site_id = a
        db.session.add(Note(text="de A"))
        db.session.commit()
        g.site_id = None
        assert db.session.scalars(select(Note)).all() == []
        with pytest.raises(RuntimeError):
            db.session.add(Note(text="sin sitio"))
            db.session.flush()
        db.session.rollback()


def test_update_y_delete_masivos_respetan_el_sitio(app, two_sites):
    a, b = two_sites
    with app.app_context():
        for site, text in [(a, "de A"), (b, "de B")]:
            g.site_id = site
            db.session.add(Note(text=text))
            db.session.commit()
        g.site_id = b
        db.session.execute(db.delete(Note))
        db.session.commit()
        g.site_id = a
        assert [n.text for n in db.session.scalars(select(Note))] == ["de A"]


def test_auditoria_de_otro_sitio_no_se_ve(app, auth_client, two_sites):
    a, b = two_sites
    with app.app_context():
        g.site_id = a
        db.session.get(Site, a).name = "A editado"
        db.session.commit()
        g.site_id = b
        rows = db.session.scalars(select(AuditLog)).all()
        assert all(r.site_id in (b, None) for r in rows)
        assert not any(r.object_label == "A editado" for r in rows)

    from tests.conftest import post

    post(auth_client, "/sitios/activo", {"site_id": b}, form_url="/")
    html = auth_client.get("/auditoria").get_data(as_text=True)
    assert "Sitio «A editado»" not in html
    assert "Inicio de sesión" in html  # los accesos no tienen sitio y siempre se ven
    post(auth_client, "/sitios/activo", {"site_id": a}, form_url="/")
    assert "Sitio «A editado»" in auth_client.get("/auditoria").get_data(as_text=True)
