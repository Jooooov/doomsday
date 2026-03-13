from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, Float, Boolean, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Owner — either user (personal) or family group
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    family_group_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("family_groups.id", ondelete="CASCADE"), nullable=True, index=True)

    # Content
    item_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    # Deterministic formula
    formula: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    formula_variables: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    calculated_quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="not_started")  # not_started / partial / complete
    progress: Mapped[float] = mapped_column(Float, default=0.0)

    # Family features
    assigned_to: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    origin: Mapped[str] = mapped_column(String(10), default="personal")  # personal / family

    # Content freshness
    is_new_recommendation: Mapped[bool] = mapped_column(Boolean, default=False)
    content_version: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    family_group: Mapped[Optional["FamilyGroup"]] = relationship("FamilyGroup", back_populates="checklist_items")
