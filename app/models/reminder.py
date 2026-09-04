import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

class Reminder(Base):
    """
    Controle de Contas a Pagar / Receber e Lembretes com notificação no Telegram
    """
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    title = Column(String, nullable=False)
    amount = Column(Float, default=0.0)
    type = Column(String, default="to_pay")  # 'to_pay' (a pagar) ou 'to_receive' (a receber)
    due_date = Column(DateTime, nullable=False)
    reminder_hours_before = Column(Integer, default=24) # 1, 2, 24 horas antes
    recurrence = Column(String, default="none")  # 'none', 'monthly', 'weekly', 'yearly'
    status = Column(String, default="pending")  # 'pending', 'paid', 'cancelled'
    
    last_notified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    workspace = relationship("Workspace", back_populates="reminders")
