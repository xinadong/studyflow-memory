from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class KnowledgeStateRecord(Base):
    __tablename__ = "knowledge_states"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    course: Mapped[str] = mapped_column(String(255), index=True)
    knowledge_point: Mapped[str] = mapped_column(String(255), index=True)
    understanding_level: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
