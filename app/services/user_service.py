import logging
import uuid
import re
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.models import User, Workspace, WorkspaceMember
from app.services.auth_service import AuthService

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
                    "phone": u.phone or "",
                    "telegram_id": u.telegram_id or "",
                    "system_role": u.system_role or "visualizador",
                    "role": m.role or "member",
                    "is_active": u.is_active if u.is_active is not None else True,
                    "is_admin_default": bool(u.is_admin_default),
                    "must_change_password": bool(u.must_change_password),
                    "joined_at": m.joined_at,
                    "workspace_id": workspace_id
                })
        return result

    @staticmethod
    def get_all_users(db: Session) -> List[Dict[str, Any]]:
        """Retorna todos os usuários cadastrados no sistema com suas roles e status"""
        users = db.query(User).order_by(User.id.asc()).all()
        result = []
        for u in users:
            result.append({
                "id": u.id,
                "name": u.name or "Sem Nome",
                "username": u.username or "",
                "phone": u.phone or "",
                "telegram_id": u.telegram_id or "",
                "system_role": u.system_role or "visualizador",
                "is_active": bool(u.is_active),
                "is_admin_default": bool(u.is_admin_default),
                "must_change_password": bool(u.must_change_password),
                "created_at": u.created_at.strftime("%d/%m/%Y %H:%M") if u.created_at else ""
            })
        return result

    @staticmethod
    def create_system_user(
        db: Session,
        name: str,
        username: str,
        phone: str,
        system_role: str = "visualizador",
        initial_password: Optional[str] = None,
        telegram_id: Optional[str] = None,
        workspace_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Cria um novo usuário no sistema com telefone obrigatório e role de acesso"""
        name_clean = name.strip() if name else ""
        username_clean = username.strip().lstrip("@").lower() if username else ""
        phone_clean = phone.strip() if phone else ""

        if not name_clean:
            raise ValueError("O nome do usuário é obrigatório.")
        if not username_clean:
            raise ValueError("O nome de usuário (login) é obrigatório.")
        if not phone_clean:
            raise ValueError("O número de telefone é obrigatório para notificações e recuperação de senha.")

        # Validação de unicidade do username
        existing_user = db.query(User).filter(User.username.ilike(username_clean)).first()
        if existing_user:
            raise ValueError(f"O nome de usuário '@{username_clean}' já está em uso.")

        # Validação de role válida
        valid_roles = ["administrador", "moderador", "visualizador"]
        role_clean = system_role.lower() if system_role else "visualizador"
        if role_clean not in valid_roles:
            role_clean = "visualizador"

        # Senha inicial padrão caso não fornecida
        plain_pwd = initial_password.strip() if initial_password and initial_password.strip() else "mudar123"
        pwd_hash = AuthService.hash_password(plain_pwd)

        # Telegram ID placeholder
        tg_id = telegram_id.strip() if telegram_id and telegram_id.strip() else f"user_{username_clean}_{uuid.uuid4().hex[:6]}"

        # Determina workspace padrão
        if not workspace_id:
            ws = db.query(Workspace).first()
            target_ws_id = ws.id if ws else None
        else:
            target_ws_id = workspace_id

        new_user = User(
            name=name_clean,
            username=username_clean,
            phone=phone_clean,
            telegram_id=tg_id,
            password_hash=pwd_hash,
            system_role=role_clean,
            is_admin_default=False,
            must_change_password=True,  # Obriga a troca no primeiro acesso
            is_active=True,
            current_workspace_id=target_ws_id
        )
        db.add(new_user)
        db.flush()

        # Vincula ao workspace
        if target_ws_id:
            member = WorkspaceMember(
                workspace_id=target_ws_id,
                user_id=new_user.id,
                role="admin" if role_clean == "administrador" else "member"
            )
            db.add(member)

        db.commit()
        db.refresh(new_user)

        return {
            "success": True,
            "id": new_user.id,
            "name": new_user.name,
            "username": new_user.username,
            "phone": new_user.phone,
            "system_role": new_user.system_role,
            "must_change_password": new_user.must_change_password,
            "initial_password": plain_pwd
        }

    @staticmethod
    def update_system_user(
        db: Session,
        user_id: int,
        name: Optional[str] = None,
        username: Optional[str] = None,
        phone: Optional[str] = None,
        system_role: Optional[str] = None,
        telegram_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        new_password: Optional[str] = None
    ) -> Dict[str, Any]:
        """Atualiza os dados de um usuário existente com checagem de segurança do admin padrão"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("Usuário não encontrado.")

        # Segurança: o admin padrão não pode ser inativado nem ter sua role alterada
        if user.is_admin_default:
            if is_active is False:
                raise ValueError("O usuário Administrador Padrão não pode ser inativado.")
            if system_role and system_role.lower() != "administrador":
                raise ValueError("A permissão do Administrador Padrão não pode ser alterada.")

        if name is not None and name.strip():
            user.name = name.strip()

        if username is not None and username.strip():
            u_clean = username.strip().lstrip("@").lower()
            if u_clean != user.username:
                existing = db.query(User).filter(User.username.ilike(u_clean), User.id != user.id).first()
                if existing:
                    raise ValueError(f"O nome de usuário '@{u_clean}' já está em uso.")
                # Se não for admin_system padrão, permite mudar username
                if not user.is_admin_default:
                    user.username = u_clean

        if phone is not None:
            if not phone.strip():
                raise ValueError("O número de telefone é obrigatório.")
            user.phone = phone.strip()

        if telegram_id is not None and telegram_id.strip():
            user.telegram_id = telegram_id.strip()

        if system_role is not None and not user.is_admin_default:
            role_clean = system_role.lower()
            if role_clean in ["administrador", "moderador", "visualizador"]:
                user.system_role = role_clean

        if is_active is not None and not user.is_admin_default:
            user.is_active = is_active
            if not is_active:
                user.is_telegram_authenticated = False

        if new_password and new_password.strip():
            user.password_hash = AuthService.hash_password(new_password.strip())
            user.must_change_password = False
            user.is_telegram_authenticated = False

        db.commit()
        db.refresh(user)

        return {
            "success": True,
            "id": user.id,
            "name": user.name,
            "username": user.username,
            "phone": user.phone,
            "system_role": user.system_role,
            "is_active": user.is_active
        }

    @staticmethod
    def toggle_user_status(db: Session, user_id: int) -> Dict[str, Any]:
        """Alterna status entre ativo e inativo com proteção para o admin padrão"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("Usuário não encontrado.")

        if user.is_admin_default:
            raise ValueError("O usuário Administrador Padrão do sistema não pode ser inativado.")

        user.is_active = not bool(user.is_active)
        if not user.is_active:
            user.is_telegram_authenticated = False

        db.commit()
        db.refresh(user)

        return {
            "success": True,
            "id": user.id,
            "is_active": user.is_active,
            "message": f"Usuário {user.name} {'ativado' if user.is_active else 'inativado'} com sucesso."
        }

    @staticmethod
    def change_user_password(db: Session, user_id: int, new_password: str) -> bool:
        """Altera a senha do usuário e desmarca a flag must_change_password"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("Usuário não encontrado.")

        if not new_password or len(new_password.strip()) < 4:
            raise ValueError("A nova senha deve ter no mínimo 4 caracteres.")

        user.password_hash = AuthService.hash_password(new_password.strip())
        user.must_change_password = False
        user.temp_password = None
        user.temp_password_expires_at = None
        user.is_telegram_authenticated = False

        db.commit()
        return True
