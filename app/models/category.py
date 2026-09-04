from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False, default="expense")  # 'expense' ou 'income'
    icon = Column(String, default="🏷️")
    color = Column(String, default="#6366f1")
    monthly_budget = Column(Float, default=0.0)

    # Relationships
    workspace = relationship("Workspace", back_populates="categories")
    transactions = relationship("Transaction", back_populates="category")
