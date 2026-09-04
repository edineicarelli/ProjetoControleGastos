import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

class Goal(Base):
    """
    Metas e Caixinhas Financeiras (ex: Reserva de Emergência, Viagem, Carro Novo)
    """
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)

    title = Column(String, nullable=False)
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, default=0.0)
    deadline = Column(DateTime, nullable=True)
    icon = Column(String, default="🎯")
    color = Column(String, default="#10b981")
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    workspace = relationship("Workspace", back_populates="goals")

    @property
    def progress_percentage(self) -> float:
        if self.target_amount <= 0:
            return 100.0 if self.current_amount >= 0 else 0.0
        pct = (self.current_amount / self.target_amount) * 100
        return min(round(pct, 1), 100.0)
