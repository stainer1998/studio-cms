from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Auditable, SiteScoped, utcnow
from app.extensions import db

STATUSES = {"borrador": "Borrador", "listo": "Listo para exportar"}


def empty_schema():
    return {"type": "object", "required": [], "properties": {}}


class ContentType(SiteScoped, Auditable, db.Model):
    __tablename__ = "content_types"
    __table_args__ = (UniqueConstraint("site_id", "key"),)
    audit_type = "Modelo"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    key: Mapped[str] = mapped_column(String(60))
    # `json` y no `jsonb`: conserva el orden de las propiedades, que es el orden de los campos.
    # Se reemplaza entero en cada cambio (no se muta en el lugar).
    schema: Mapped[dict] = mapped_column(JSON, default=empty_schema)
    slug_source: Mapped[str | None] = mapped_column(String(60))

    @property
    def audit_label(self):
        return self.name

    @property
    def fields(self):
        """[(clave, propiedad)] en orden."""
        return list(self.schema["properties"].items())

    @property
    def slug_field(self):
        return next((k for k, p in self.fields if p["x-type"] == "slug"), None)

    @property
    def title_field(self):
        return next((k for k, p in self.fields if p["x-type"] == "text"), None)


class Entry(SiteScoped, Auditable, db.Model):
    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint("content_type_id", "slug"),
        CheckConstraint("status IN ('borrador', 'listo')", name="status"),
        Index("ix_entries_data", "data", postgresql_using="gin"),
    )
    audit_type = "Entrada"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_type_id: Mapped[int] = mapped_column(ForeignKey("content_types.id"), index=True)
    slug: Mapped[str | None] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="borrador")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    content_type: Mapped[ContentType] = relationship(lazy="joined")

    @property
    def title(self):
        key = self.content_type.title_field
        return (key and self.data.get(key)) or self.slug or f"Entrada {self.id}"

    @property
    def audit_label(self):
        return self.title


class EntryVersion(SiteScoped, db.Model):
    __tablename__ = "entry_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
