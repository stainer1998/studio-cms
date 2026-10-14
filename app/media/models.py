from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Auditable, SiteScoped, utcnow
from app.extensions import db

# Variantes WebP por ancho (RF-14). Los nombres son los que usa media_url() en las plantillas.
VARIANTS = {"miniatura": 320, "mediana": 800, "grande": 1600}


class Media(SiteScoped, Auditable, db.Model):
    __tablename__ = "media"
    audit_type = "Medio"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(60))
    size: Mapped[int]
    width: Mapped[int | None]
    height: Mapped[int | None]
    alt_text: Mapped[str] = mapped_column(String(300), default="")
    # None mientras se generan; {nombre: {"width", "height"}} al terminar; {"error": "…"} si falla.
    variants: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @property
    def audit_label(self):
        return self.filename

    @property
    def is_image(self):
        return self.mime.startswith("image/")

    @property
    def pending(self):
        return self.is_image and self.variants is None

    @property
    def failed(self):
        return bool(self.variants and "error" in self.variants)

    def has_variant(self, name):
        return bool(self.variants) and name in self.variants


class MediaUsage(SiteScoped, db.Model):
    """Dónde se usa cada medio. Sin cascada: un medio en uso no se puede eliminar (RF-15)."""

    __tablename__ = "media_usages"

    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id"), index=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.id", ondelete="CASCADE"), index=True)

    entry = relationship("Entry", lazy="joined")
