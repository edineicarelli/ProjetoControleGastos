import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    
    type = Column(String, nullable=False)  # 'expense' (despesa) ou 'income' (receita)
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=False)
    payment_method = Column(String, default="Outro")  # Dinheiro, Pix, Cartão de Crédito, Cartão de Débito, Boleto, etc.
    
    transaction_date = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="completed")  # 'completed', 'pending'
    receipt_url = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    workspace = relationship("Workspace", back_populates="transactions")
    user = relationship("User", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")
