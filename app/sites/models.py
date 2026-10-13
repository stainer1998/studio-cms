from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Auditable, utcnow
from app.extensions import db


class Site(Auditable, db.Model):
    __tablename__ = "sites"
    audit_type = "Sitio"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    key: Mapped[str] = mapped_column(String(60), unique=True)
    domain: Mapped[str] = mapped_column(String(253))
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @property
    def audit_label(self):
        return self.name

    @property
    def audit_site_id(self):
        return self.id
