import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models import Account, Transaction, Workspace

DEFAULT_ACCOUNTS = [
    {"name": "Dinheiro", "type": "cash", "icon": "💵", "color": "#10b981"},
    {"name": "Banco do Brasil", "type": "checking", "icon": "🟡", "color": "#fbbf24"},
    {"name": "Caixa", "type": "checking", "icon": "🔵", "color": "#3b82f6"},
    {"name": "Santander", "type": "checking", "icon": "🔴", "color": "#ef4444"},
    {"name": "Nubank", "type": "checking", "icon": "🟣", "color": "#8b5cf6"},
    {"name": "Itaú", "type": "checking", "icon": "🟠", "color": "#f97316"},
]

class AccountService:
    @staticmethod
    def seed_default_accounts(db: Session, workspace_id: int):
        """Cria as contas padrão para um novo workspace se ainda não existirem"""
        existing = db.query(Account).filter(Account.workspace_id == workspace_id).first()
        if not existing:
            for acc in DEFAULT_ACCOUNTS:
                db.add(Account(
                    workspace_id=workspace_id,
                    name=acc["name"],
                    type=acc["type"],
                    icon=acc["icon"],
                    color=acc["color"],
                    initial_balance=0.0,
                    current_balance=0.0
                ))
            db.commit()

    @staticmethod
    def get_accounts(db: Session, workspace_id: int, active_only: bool = False) -> List[Account]:
        """Retorna as contas do workspace, criando as padrões se vazio"""
        query = db.query(Account).filter(Account.workspace_id == workspace_id)
        if active_only:
            query = query.filter(Account.is_active == True)
        accounts = query.order_by(Account.id.asc()).all()
        if not accounts and not active_only:
            AccountService.seed_default_accounts(db, workspace_id)
            accounts = db.query(Account).filter(Account.workspace_id == workspace_id).order_by(Account.id.asc()).all()
        return accounts

    @staticmethod
    def create_account(
        db: Session,
        workspace_id: int,
        name: str,
        type: str = "checking",
        initial_balance: float = 0.0,
        icon: str = "🏦",
        color: str = "#6366f1",
        is_active: bool = True
    ) -> Account:
        acc = Account(
            workspace_id=workspace_id,
            name=name.strip(),
            type=type,
            initial_balance=initial_balance,
            current_balance=initial_balance,
            icon=icon or "🏦",
            color=color or "#6366f1",
            is_active=is_active
        )
        db.add(acc)
        db.commit()
        db.refresh(acc)

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(workspace_id)
        except Exception:
            pass

        return acc

    @staticmethod
    def update_account(
        db: Session,
        account_id: int,
        name: Optional[str] = None,
        type: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        initial_balance: Optional[float] = None,
        is_active: Optional[bool] = None
    ) -> Optional[Account]:
        """Atualiza os dados de uma conta bancária e recalcula o saldo se o saldo inicial mudar"""
        acc = db.query(Account).filter(Account.id == account_id).first()
        if not acc:
            return None

        if name is not None:
            acc.name = name.strip()
        if type is not None:
            acc.type = type
        if icon is not None:
            acc.icon = icon
        if color is not None:
            acc.color = color
        if is_active is not None:
            acc.is_active = is_active
        if initial_balance is not None:
            diff = initial_balance - (acc.initial_balance or 0.0)
            acc.initial_balance = initial_balance
            acc.current_balance = (acc.current_balance or 0.0) + diff

        ws_id = acc.workspace_id
        db.commit()
        db.refresh(acc)

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(ws_id)
        except Exception:
            pass

        return acc

    @staticmethod
    def toggle_account_active(db: Session, account_id: int) -> Optional[Account]:
        """Inativa ou reativa uma conta bancária"""
        acc = db.query(Account).filter(Account.id == account_id).first()
        if not acc:
            return None
        acc.is_active = not (acc.is_active if acc.is_active is not None else True)
        ws_id = acc.workspace_id
        db.commit()
        db.refresh(acc)

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(ws_id)
        except Exception:
            pass

        return acc

    @staticmethod
    def delete_account(db: Session, account_id: int) -> bool:
        """Exclui uma conta bancária, desvinculando transações associadas sem apagá-las"""
        acc = db.query(Account).filter(Account.id == account_id).first()
        if not acc:
            return False

        ws_id = acc.workspace_id
        # Desvincula transações associadas
        db.query(Transaction).filter(Transaction.account_id == account_id).update({"account_id": None})
        db.delete(acc)
        db.commit()

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(ws_id)
        except Exception:
            pass

        return True

    @staticmethod
    def find_account_by_name(db: Session, workspace_id: int, name: str) -> Optional[Account]:
        """Localiza uma conta pelo nome ou substring (ex: 'caixa', 'bb', 'santander', 'nubank')"""
        name_clean = name.lower().strip()
        accounts = AccountService.get_accounts(db, workspace_id)
        
        # Mapeamento de apelidos comuns
        aliases = {
            "bb": "banco do brasil",
            "bancodobrasil": "banco do brasil",
            "nu": "nubank",
            "caixa economica": "caixa",
            "cef": "caixa",
            "itau": "itaú",
            "cash": "dinheiro",
            "carteira": "dinheiro",
            "especie": "dinheiro",
            "em especie": "dinheiro"
        }
        target = aliases.get(name_clean, name_clean)

        for acc in accounts:
            acc_name_lower = acc.name.lower()
            if acc_name_lower in target or target in acc_name_lower:
                return acc
        return None

    @staticmethod
    def set_transaction_account(db: Session, transaction_id: int, account_id: int) -> Optional[Transaction]:
        """Vincula uma transação a uma conta específica e recalcula o saldo da conta"""
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        acc = db.query(Account).filter(Account.id == account_id).first()
        if not tx or not acc:
            return None

        # Se já tinha outra conta antes, estorna o saldo anterior
        if tx.account_id and tx.account_id != account_id:
            old_acc = db.query(Account).filter(Account.id == tx.account_id).first()
            if old_acc:
                if tx.type == "income":
                    old_acc.current_balance -= tx.amount
                else:
                    old_acc.current_balance += tx.amount

        # Atualiza a conta na transação
        tx.account_id = acc.id
        tx.payment_method = acc.name

        # Atualiza o saldo da nova conta
        if tx.type == "income":
            acc.current_balance += tx.amount
        else:
            acc.current_balance -= tx.amount

        db.commit()
        db.refresh(tx)
        return tx

    @staticmethod
    def transfer_between_accounts(
        db: Session,
        workspace_id: int,
        user_id: int,
        from_account_id: int,
        to_account_id: int,
        amount: float,
        description: Optional[str] = None,
        transaction_date: Optional[datetime.datetime] = None
    ) -> Dict[str, Any]:
        """Realiza transferência entre duas contas ou carteiras do workspace"""
        from app.models import Category
        
        if from_account_id == to_account_id:
            raise ValueError("A conta de origem e a conta de destino devem ser diferentes.")
        
        if amount <= 0:
            raise ValueError("O valor da transferência deve ser maior que zero.")

        from_acc = db.query(Account).filter(Account.id == from_account_id, Account.workspace_id == workspace_id).first()
        to_acc = db.query(Account).filter(Account.id == to_account_id, Account.workspace_id == workspace_id).first()

        if not from_acc:
            raise ValueError("Conta de origem não encontrada.")
        if not to_acc:
            raise ValueError("Conta de destino não encontrada.")

        # Categoria de transferência
        category = db.query(Category).filter(
            Category.workspace_id == workspace_id,
            Category.name.ilike("Transferência")
        ).first()

        if not category:
            category = Category(
                workspace_id=workspace_id,
                name="Transferência",
                type="expense",
                icon="🔄",
                color="#6366f1"
            )
            db.add(category)
            db.flush()

        tx_date = transaction_date or datetime.datetime.utcnow()
        desc_suffix = f" - {description.strip()}" if (description and description.strip()) else ""

        # Lançamento de saída (Débito da conta de origem)
        tx_out = Transaction(
            workspace_id=workspace_id,
            user_id=user_id,
            category_id=category.id,
            account_id=from_acc.id,
            type="expense",
            amount=abs(amount),
            description=f"Transferência para {to_acc.icon} {to_acc.name}{desc_suffix}",
            payment_method=from_acc.name,
            transaction_date=tx_date,
            status="completed",
            notes=f"transfer_to_account_id:{to_acc.id}"
        )
        db.add(tx_out)

        # Lançamento de entrada (Crédito na conta de destino)
        tx_in = Transaction(
            workspace_id=workspace_id,
            user_id=user_id,
            category_id=category.id,
            account_id=to_acc.id,
            type="income",
            amount=abs(amount),
            description=f"Transferência recebida de {from_acc.icon} {from_acc.name}{desc_suffix}",
            payment_method=to_acc.name,
            transaction_date=tx_date,
            status="completed",
            notes=f"transfer_from_account_id:{from_acc.id}"
        )
        db.add(tx_in)

        # Atualiza os saldos acumulados de ambas as contas
        from_acc.current_balance = (from_acc.current_balance or 0.0) - abs(amount)
        to_acc.current_balance = (to_acc.current_balance or 0.0) + abs(amount)

        db.commit()
        db.refresh(from_acc)
        db.refresh(to_acc)
        db.refresh(tx_out)
        db.refresh(tx_in)

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(workspace_id)
        except Exception:
            pass

        return {
            "success": True,
            "from_account": from_acc,
            "to_account": to_acc,
            "amount": amount,
            "tx_out": tx_out,
            "tx_in": tx_in
        }

    @staticmethod
    def recalculate_account_balances(db: Session, workspace_id: int):
        """Recalcula os saldos de todas as contas a partir das transações existentes"""
        accounts = db.query(Account).filter(Account.workspace_id == workspace_id).all()
        for acc in accounts:
            income_total = sum(t.amount for t in acc.transactions if t.type == "income")
            expense_total = sum(t.amount for t in acc.transactions if t.type == "expense")
            acc.current_balance = (acc.initial_balance or 0.0) + income_total - expense_total
        db.commit()

