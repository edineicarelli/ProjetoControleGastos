import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    current_workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    current_workspace = relationship("Workspace", foreign_keys=[current_workspace_id])
    memberships = relationship("WorkspaceMember", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user")
