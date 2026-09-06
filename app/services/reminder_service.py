import datetime
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Reminder, User, Workspace, WorkspaceMember

logger = logging.getLogger(__name__)

class ReminderService:
    @staticmethod
    def find_duplicate_reminder(
        db: Session,
        workspace_id: int,
        amount: float,
        due_date: datetime.datetime,
        title: Optional[str] = None
    ) -> Optional[Reminder]:
        """
        Verifica se já existe um lembrete/conta cadastrada no mesmo workspace
        com o mesmo valor e mesma data de vencimento (mesmo dia/mês/ano).
        """
        start_of_day = datetime.datetime(due_date.year, due_date.month, due_date.day, 0, 0, 0)
        end_of_day = datetime.datetime(due_date.year, due_date.month, due_date.day, 23, 59, 59)
        
        reminders = db.query(Reminder).filter(
            Reminder.workspace_id == workspace_id,
            Reminder.status.in_(["pending", "paid"]),
            Reminder.due_date >= start_of_day,
            Reminder.due_date <= end_of_day
        ).all()

        for r in reminders:
            if abs(r.amount - float(amount)) < 0.01:
                return r

        return None

    @staticmethod
    def create_reminder(
        db: Session,
        workspace_id: int,
        user_id: int,
        title: str,
        amount: float,
        due_date: datetime.datetime,
        type: str = "to_pay",
        recurrence: str = "none",
        reminder_hours_before: int = 24
    ) -> Reminder:
        reminder = Reminder(
            workspace_id=workspace_id,
            user_id=user_id,
            title=title.strip(),
            amount=amount,
            type=type,
            due_date=due_date,
            recurrence=recurrence,
            reminder_hours_before=reminder_hours_before,
            status="pending"
        )
        db.add(reminder)
        db.commit()
        db.refresh(reminder)
        return reminder

    @staticmethod
    def get_upcoming_reminders(db: Session, workspace_id: int, days_ahead: Optional[int] = None) -> List[Reminder]:
        query = db.query(Reminder).filter(
            Reminder.workspace_id == workspace_id,
            Reminder.status == "pending"
        )
        if days_ahead is not None:
            now = datetime.datetime.utcnow()
            limit_date = now + datetime.timedelta(days=days_ahead)
            query = query.filter(Reminder.due_date <= limit_date)
            
        return query.order_by(Reminder.due_date.asc()).all()

    @staticmethod
    def mark_as_paid(db: Session, reminder_id: int) -> Optional[Reminder]:
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
        if not reminder:
            return None
        reminder.status = "paid"

        # Se for recorrente mensal, agenda a próxima fatura automaticamente
        if reminder.recurrence == "monthly":
            next_month = reminder.due_date.month + 1 if reminder.due_date.month < 12 else 1
            next_year = reminder.due_date.year if reminder.due_date.month < 12 else reminder.due_date.year + 1
            day = min(reminder.due_date.day, 28)
            next_due = reminder.due_date.replace(year=next_year, month=next_month, day=day)
            
            new_reminder = Reminder(
                workspace_id=reminder.workspace_id,
                user_id=reminder.user_id,
                title=reminder.title,
                amount=reminder.amount,
                type=reminder.type,
                due_date=next_due,
                recurrence="monthly",
                reminder_hours_before=reminder.reminder_hours_before,
                status="pending"
            )
            db.add(new_reminder)

        db.commit()
        db.refresh(reminder)
        return reminder

    @staticmethod
    async def check_and_send_due_reminders(bot_app):
        """Job executado periodicamente pelo agendador (APScheduler) para notificar contas no Telegram"""
        db = SessionLocal()
        try:
            now = datetime.datetime.utcnow()
            # Busca lembretes pendentes que vencem nas próximas 24h e ainda não foram notificados hoje
            tomorrow = now + datetime.timedelta(hours=24)
            reminders = db.query(Reminder).filter(
                Reminder.status == "pending",
                Reminder.due_date <= tomorrow
            ).all()

            for r in reminders:
                if r.last_notified_at and (now - r.last_notified_at).total_seconds() < 43200: # 12 horas
                    continue

                # Busca membros do workspace para notificar
                members = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == r.workspace_id).all()
                for member in members:
                    user = db.query(User).filter(User.id == member.user_id).first()
                    if user and user.telegram_id and bot_app:
                        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ Marcar como Pago", callback_data=f"pay_reminder_{r.id}")],
                            [InlineKeyboardButton("⏳ Adiar 1 Dia", callback_data=f"snooze_reminder_{r.id}")]
                        ])
                        from app.utils import format_currency_br
                        tipo_str = "🔴 Conta a Pagar" if r.type == "to_pay" else "🟢 Conta a Receber"
                        msg = (
                            f"🔔 *Lembrete de Vencimento!*\n\n"
                            f"{tipo_str}: *{r.title}*\n"
                            f"💰 Valor: *{format_currency_br(r.amount)}*\n"
                            f"📅 Vencimento: *{r.due_date.strftime('%d/%m/%Y')}*\n\n"
                            f"Evite juros e mantenha seu fluxo em dia!"
                        )
                        try:
                            await bot_app.bot.send_message(
                                chat_id=user.telegram_id,
                                text=msg,
                                parse_mode="Markdown",
                                reply_markup=keyboard
                            )
                        except Exception as e:
                            logger.error(f"Erro ao enviar lembrete para telegram {user.telegram_id}: {e}")

                r.last_notified_at = now
            db.commit()
        except Exception as e:
            logger.error(f"Erro no job de lembretes: {e}")
        finally:
            db.close()
