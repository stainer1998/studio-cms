from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.extensions import db


def utcnow():
    return datetime.now(UTC)


class SiteScoped:
    """Tabla de contenido de un sitio. Las consultas se filtran solas por el sitio activo."""

    @declared_attr
    def site_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("sites.id"), index=True)


class Auditable:
    """Su creación, edición y eliminación quedan en audit_log automáticamente."""

    audit_type: str  # nombre visible del tipo de objeto, en español

    @property
    def audit_label(self) -> str:
        return str(self.id)

    @property
    def audit_site_id(self) -> int | None:
        return self.site_id


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_site_created", "site_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nulo para eventos sin sitio, como los inicios de sesión.
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40))
    object_type: Mapped[str | None] = mapped_column(String(40))
    object_id: Mapped[int | None]
    # Nombre del objeto al momento de la acción, para que siga legible si se elimina.
    object_label: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    site = relationship("Site", lazy="joined")
    user = relationship("User", lazy="joined")
