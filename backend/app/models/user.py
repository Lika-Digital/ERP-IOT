"""User, UserMarinaAccess, and audit log models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from ..database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    password_hash = Column(String(500), nullable=False)
    full_name = Column(String(200), nullable=True)

    # Role: super_admin (all marinas) | marina_manager (only assigned marinas)
    role = Column(String(50), nullable=False, default="marina_manager")

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    # Relationships
    marina_access = relationship(
        "UserMarinaAccess",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserMarinaAccess.user_id",
    )


class UserMarinaAccess(Base):
    """Junction table: which marinas a marina_manager can access."""
    __tablename__ = "user_marina_access"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    marina_id = Column(Integer, ForeignKey("marinas.id", ondelete="CASCADE"), primary_key=True)
    granted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="marina_access", foreign_keys=[user_id])
