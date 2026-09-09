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
    items = relationship("TransactionItem", back_populates="transaction", cascade="all, delete-orphan", order_by="TransactionItem.id")

    @property
    def items_count(self) -> int:
        return len(self.items) if self.items else 0

    @property
    def has_items(self) -> bool:
        return bool(self.items and len(self.items) > 0)

class TransactionItem(Base):
    """
    Itens individuais/produtos de uma transação (ex: itens de cupom fiscal de mercado, farmácia, etc.)
    Permite analisar o que foi comprado item a item com o valor total gasto.
    """
    __tablename__ = "transaction_items"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String, nullable=False)
    quantity = Column(Float, default=1.0)
    unit = Column(String, default="un")  # un, kg, g, l, pct, cx, etc.
    unit_price = Column(Float, default=0.0)
    total_price = Column(Float, default=0.0)
    category = Column(String, default="Geral")  # Categoria específica do item (Mercearia, Hortifruti, Limpeza, etc.)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    transaction = relationship("Transaction", back_populates="items")

