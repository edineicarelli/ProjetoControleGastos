import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import Goal

class GoalService:
    @staticmethod
    def create_goal(
        db: Session,
        workspace_id: int,
        title: str,
        target_amount: float,
        current_amount: float = 0.0,
        deadline: Optional[datetime.datetime] = None,
        icon: str = "🎯"
    ) -> Goal:
        goal = Goal(
            workspace_id=workspace_id,
            title=title.strip(),
            target_amount=target_amount,
            current_amount=current_amount,
            deadline=deadline,
            icon=icon
        )
        db.add(goal)
        db.commit()
        db.refresh(goal)
        return goal

    @staticmethod
    def deposit(db: Session, goal_id: int, amount: float) -> Optional[Goal]:
        goal = db.query(Goal).filter(Goal.id == goal_id).first()
        if not goal:
            return None
        goal.current_amount += abs(amount)
        if goal.current_amount >= goal.target_amount:
            goal.is_completed = True
        db.commit()
        db.refresh(goal)
        return goal

    @staticmethod
    def deposit_by_name(db: Session, workspace_id: int, goal_name: str, amount: float) -> Optional[Goal]:
        # Busca meta que contenha o termo
        goal = db.query(Goal).filter(
            Goal.workspace_id == workspace_id,
            Goal.title.ilike(f"%{goal_name.strip()}%")
        ).first()

        if not goal:
            # Cria a meta automaticamente com alvo padrão
            goal = Goal(
                workspace_id=workspace_id,
                title=goal_name.strip().title(),
                target_amount=max(amount * 5, 1000.0),
                current_amount=abs(amount),
                icon="🎯"
            )
            db.add(goal)
            db.commit()
            db.refresh(goal)
            return goal

        goal.current_amount += abs(amount)
        if goal.current_amount >= goal.target_amount:
            goal.is_completed = True
        db.commit()
        db.refresh(goal)
        return goal

    @staticmethod
    def get_progress_bar(percentage: float, length: int = 10) -> str:
        filled = int(round(length * min(percentage, 100) / 100))
        empty = length - filled
        return f"[{'█' * filled}{'░' * empty}] {percentage:.1f}%"
