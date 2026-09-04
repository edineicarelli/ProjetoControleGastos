import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.models import Workspace, WorkspaceMember, User
from app.services.finance_service import FinanceService
from app.services.account_service import AccountService

logger = logging.getLogger(__name__)

class WorkspaceService:
    @staticmethod
    def get_all_workspaces(db: Session) -> List[Workspace]:
        return db.query(Workspace).order_by(Workspace.id.desc()).all()

    @staticmethod
    def get_workspace_by_id(db: Session, workspace_id: int) -> Optional[Workspace]:
        return db.query(Workspace).filter(Workspace.id == workspace_id).first()

    @staticmethod
    def create_workspace(db: Session, user_id: int, name: str, ws_type: str = "personal", currency: str = "R$") -> Workspace:
        """Cria um novo perfil/workspace, associa o usuário e inicializa categorias e contas padrão"""
        ws = Workspace(
            name=name.strip(),
            type=ws_type,
            currency=currency
        )
        db.add(ws)
        db.flush()

        # Vincula membro
        member = WorkspaceMember(
            workspace_id=ws.id,
            user_id=user_id,
            role="owner"
        )
        db.add(member)

        # Inicializa categorias e contas padrão
        FinanceService._seed_categories(db, ws.id)
        AccountService.seed_default_accounts(db, ws.id)

        # Atualiza usuário para ter esse workspace se não tiver nenhum ativo
        user = db.query(User).filter(User.id == user_id).first()
        if user and not user.current_workspace_id:
            user.current_workspace_id = ws.id

        db.commit()
        db.refresh(ws)
        logger.info(f"Workspace '{name}' (ID: {ws.id}) criado com sucesso para usuário ID: {user_id}")
        return ws

    @staticmethod
    def update_workspace(db: Session, workspace_id: int, name: str, ws_type: Optional[str] = None) -> Optional[Workspace]:
        """Atualiza nome e tipo do workspace"""
        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not ws:
            return None

        if name:
            ws.name = name.strip()
        if ws_type:
            ws.type = ws_type

        db.commit()
        db.refresh(ws)
        logger.info(f"Workspace ID {workspace_id} atualizado para '{ws.name}'")
        return ws

    @staticmethod
    def delete_workspace(db: Session, workspace_id: int) -> bool:
        """Exclui o workspace e seus dados vinculados em cascata"""
        # Verifica quantos workspaces existem no total
        total_ws = db.query(Workspace).count()
        if total_ws <= 1:
            raise ValueError("Não é possível excluir o único perfil existente. O sistema precisa ter pelo menos um perfil ativo.")

        ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not ws:
            return False

        # Se houver usuários cujo current_workspace_id seja este, atualiza para outro
        other_ws = db.query(Workspace).filter(Workspace.id != workspace_id).order_by(Workspace.id.desc()).first()
        if other_ws:
            users_with_current = db.query(User).filter(User.current_workspace_id == workspace_id).all()
            for u in users_with_current:
                u.current_workspace_id = other_ws.id

        db.delete(ws)
        db.commit()
        logger.info(f"Workspace ID {workspace_id} excluído com sucesso")
        return True
