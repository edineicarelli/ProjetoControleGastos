import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class ShoppingList(Base):
    """
    Lista de Mercado / Compras com checklist e integração ao fluxo financeiro
    """
    __tablename__ = "shopping_lists"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)

    title = Column(String, nullable=False, default="Compras do Mês")
    is_completed = Column(Boolean, default=False)
    total_spent = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    workspace = relationship("Workspace", back_populates="shopping_lists")
    items = relationship("ShoppingItem", back_populates="shopping_list", cascade="all, delete-orphan")

    @property
    def total_estimated(self) -> float:
        return sum(item.estimated_price * item.quantity for item in self.items)

    @property
    def total_bought(self) -> float:
        return sum(item.estimated_price * item.quantity for item in self.items if item.is_checked)

class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id = Column(Integer, primary_key=True, index=True)
    shopping_list_id = Column(Integer, ForeignKey("shopping_lists.id", ondelete="CASCADE"), nullable=False)

    name = Column(String, nullable=False)
    quantity = Column(Float, default=1.0)
    unit = Column(String, default="un")  # un, kg, g, l, pct
    estimated_price = Column(Float, default=0.0)
    is_checked = Column(Boolean, default=False)
    category = Column(String, default="Geral")

    shopping_list = relationship("ShoppingList", back_populates="items")
