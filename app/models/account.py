import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

class Account(Base):
    """
    Contas bancárias, carteiras e cartões do usuário
    (Ex: Banco do Brasil, Caixa, Santander, Nubank, Dinheiro, etc.)
    """
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)  # Ex: "Banco do Brasil", "Caixa", "Santander", "Dinheiro"
    type = Column(String, default="checking")  # checking (corrente), savings (poupança), credit_card, cash (dinheiro), investment
    initial_balance = Column(Float, default=0.0)
    current_balance = Column(Float, default=0.0)
    icon = Column(String, default="🏦")
    color = Column(String, default="#6366f1")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    workspace = relationship("Workspace", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")
