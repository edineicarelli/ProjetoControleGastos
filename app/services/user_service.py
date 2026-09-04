import logging
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.models import User, Workspace, WorkspaceMember

logger = logging.getLogger(__name__)

class UserService:
    @staticmethod
    def get_workspace_members(db: Session, workspace_id: int) -> List[Dict[str, Any]]:
        """Retorna todos os membros/usuários vinculados a um workspace específico"""
        memberships = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).all()
        result = []
        for m in memberships:
            u = m.user
            if u:
                result.append({
                    "id": u.id,
                    "member_id": m.id,
                    "name": u.name or "Sem Nome",
                    "username": u.username or "",
                    "telegram_id": u.telegram_id or "",
                    "role": m.role or "member",
                    "is_active": u.is_active if u.is_active is not None else True,
                    "joined_at": m.joined_at,
                    "workspace_id": workspace_id
                })
        return result

    @staticmethod
    def get_all_users(db: Session) -> List[User]:
        """Retorna todos os usuários cadastrados no banco de dados"""
        return db.query(User).order_by(User.id.asc()).all()

    @staticmethod
    def add_user_to_workspace(
        db: Session,
        workspace_id: int,
        name: str,
        telegram_id: Optional[str] = None,
        username: Optional[str] = None,
        role: str = "member",
        is_active: bool = True
    ) -> Dict[str, Any]:
        """Cadastra ou associa um usuário a um perfil/workspace para controle web e Telegram"""
        name_clean = name.strip() if name else "Novo Usuário"
        username_clean = username.strip().lstrip("@") if username and username.strip() else None
        tg_id_clean = str(telegram_id).strip() if telegram_id and str(telegram_id).strip() else None

        # Se não informou telegram_id, gera um placeholder temporário único
        if not tg_id_clean:
            if username_clean:
                tg_id_clean = f"pending_user_{username_clean}"
            else:
                tg_id_clean = f"user_{uuid.uuid4().hex[:8]}"

        # 1. Procura se já existe um usuário com esse telegram_id ou username
        user = None
        if tg_id_clean and not tg_id_clean.startswith("user_"):
            user = db.query(User).filter(User.telegram_id == tg_id_clean).first()
        if not user and username_clean:
            user = db.query(User).filter(User.username.ilike(username_clean)).first()

        if not user:
            user = User(
                telegram_id=tg_id_clean,
                name=name_clean,
                username=username_clean,
                is_active=is_active,
                current_workspace_id=workspace_id
            )
            db.add(user)
            db.flush()
        else:
            if name_clean:
                user.name = name_clean
            if username_clean:
                user.username = username_clean
            if tg_id_clean and not tg_id_clean.startswith("user_"):
                user.telegram_id = tg_id_clean
            user.is_active = is_active
            if not user.current_workspace_id:
                user.current_workspace_id = workspace_id

        # 2. Vincula ao workspace
        member = db.query(WorkspaceMember).filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id
        ).first()

        if not member:
            member = WorkspaceMember(
                workspace_id=workspace_id,
                user_id=user.id,
                role=role or "member"
            )
            db.add(member)
        else:
            member.role = role or member.role

        db.commit()
        db.refresh(user)
        db.refresh(member)

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(workspace_id)
        except Exception:
            pass

        return {
            "success": True,
            "user_id": user.id,
            "member_id": member.id,
            "name": user.name,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "role": member.role
        }

    @staticmethod
    def update_user_member(
        db: Session,
        workspace_id: int,
        user_id: int,
        name: Optional[str] = None,
        username: Optional[str] = None,
        telegram_id: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        """Atualiza os dados de um usuário e suas permissões no workspace"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        if name is not None:
            user.name = name.strip()
        if username is not None:
            user.username = username.strip().lstrip("@") if username.strip() else None
        if telegram_id is not None and telegram_id.strip():
            user.telegram_id = telegram_id.strip()
        if is_active is not None:
            user.is_active = is_active

        if role is not None:
            member = db.query(WorkspaceMember).filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id
            ).first()
            if member:
                member.role = role

        db.commit()
        db.refresh(user)

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(workspace_id)
        except Exception:
            pass

        return {"success": True, "user_id": user.id, "name": user.name}

    @staticmethod
    def remove_user_from_workspace(db: Session, workspace_id: int, user_id: int) -> bool:
        """Remove o acesso de um usuário ao workspace"""
        member = db.query(WorkspaceMember).filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id
        ).first()

        if not member:
            return False

        # Não permite remover se for o único dono do workspace
        if member.role == "owner":
            owner_count = db.query(WorkspaceMember).filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == "owner"
            ).count()
            if owner_count <= 1:
                raise ValueError("Não é possível remover o único proprietário deste perfil.")

        db.delete(member)
        
        # Se era o workspace atual do usuário, redireciona para outro se houver
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.current_workspace_id == workspace_id:
            other_m = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user_id).first()
            user.current_workspace_id = other_m.workspace_id if other_m else None

        db.commit()

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(workspace_id)
        except Exception:
            pass

        return True
