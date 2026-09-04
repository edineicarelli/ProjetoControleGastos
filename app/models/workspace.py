import datetime
import uuid
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Workspace(Base):
    """
    Representa o contexto de finanças:
    - 'personal' (PF - Pessoa Física)
    - 'business' (PJ - Pessoa Jurídica / Empresa)
    - 'family' (Compartilhado / Casal / Sócios)
    """
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, default="personal")  # personal, business, family
    currency = Column(String, default="R$")
    invite_code = Column(String, unique=True, default=lambda: uuid.uuid4().hex[:8].upper())
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="workspace", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="workspace", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="workspace", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="workspace", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="workspace", cascade="all, delete-orphan")
    shopping_lists = relationship("ShoppingList", back_populates="workspace", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="workspace", cascade="all, delete-orphan")

class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, default="owner")  # owner, admin, member
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)

    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", back_populates="memberships")
