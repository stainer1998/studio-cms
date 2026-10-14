from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Auditable, SiteScoped, utcnow
from app.extensions import db

MODES = {"code": "Código", "visual": "Visual"}
# Rutas con carpetas: minúsculas, números, guiones y guiones bajos, terminadas en .html.
PATH_PATTERN = r"^[a-z0-9_-]+(/[a-z0-9_-]+)*\.html$"


class Template(SiteScoped, Auditable, db.Model):
    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint("site_id", "path"),
        CheckConstraint("mode IN ('code', 'visual')", name="mode"),
    )
    audit_type = "Plantilla"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(10), default="code")
    # Lo usa la caché del motor para saber si la plantilla compilada sigue vigente.
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    @property
    def audit_label(self):
        return self.path

    @property
    def name(self):
        return self.path.rsplit("/", 1)[-1]

    @property
    def folder(self):
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""


class TemplateVersion(SiteScoped, db.Model):
    __tablename__ = "template_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
