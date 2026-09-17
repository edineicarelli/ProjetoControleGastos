import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
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
    def recalculate_account_balance(db: Session, account_id: int) -> float:
        """
        Recalcula com precisão matemática o saldo de uma conta bancária
        a partir do saldo inicial e de todas as transações cadastradas no banco de dados.
        """
        acc = db.query(Account).filter(Account.id == account_id).first()
        if not acc:
            return 0.0

        inc = float(db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
            Transaction.account_id == acc.id,
            Transaction.type == "income"
        ).scalar() or 0.0)

        exp = float(db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
            Transaction.account_id == acc.id,
            Transaction.type == "expense"
        ).scalar() or 0.0)

        acc.current_balance = round((acc.initial_balance or 0.0) + inc - exp, 2)
        db.commit()
        return acc.current_balance

    @staticmethod
    def recalculate_account_balances(db: Session, workspace_id: int):
        """
        Recalcula os saldos de todas as contas do workspace a partir do banco de dados.
        """
        accounts = db.query(Account).filter(Account.workspace_id == workspace_id).all()
        for acc in accounts:
            inc = float(db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
                Transaction.account_id == acc.id,
                Transaction.type == "income"
            ).scalar() or 0.0)

            exp = float(db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
                Transaction.account_id == acc.id,
                Transaction.type == "expense"
            ).scalar() or 0.0)

            acc.current_balance = round((acc.initial_balance or 0.0) + inc - exp, 2)
        db.commit()

    @staticmethod
    def get_accounts(db: Session, workspace_id: int, active_only: bool = False) -> List[Account]:
        """Retorna as contas do workspace, garantindo que os saldos estejam 100% calculados e íntegros"""
        query = db.query(Account).filter(Account.workspace_id == workspace_id)
        if active_only:
            query = query.filter(Account.is_active == True)
        accounts = query.order_by(Account.id.asc()).all()
        if not accounts and not active_only:
            AccountService.seed_default_accounts(db, workspace_id)
            accounts = db.query(Account).filter(Account.workspace_id == workspace_id).order_by(Account.id.asc()).all()

        # Recalcula saldos com base no banco de dados para evitar qualquer descompasso
        for acc in accounts:
            inc = float(db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
                Transaction.account_id == acc.id,
                Transaction.type == "income"
            ).scalar() or 0.0)
            exp = float(db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
                Transaction.account_id == acc.id,
                Transaction.type == "expense"
            ).scalar() or 0.0)
            acc.current_balance = round((acc.initial_balance or 0.0) + inc - exp, 2)
        db.commit()

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
        init_val = round(float(initial_balance or 0.0), 2)
        acc = Account(
            workspace_id=workspace_id,
            name=name.strip(),
            type=type,
            initial_balance=init_val,
            current_balance=init_val,
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
        """Atualiza os dados de uma conta bancária e recalcula seu saldo exato"""
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
            acc.initial_balance = round(float(initial_balance), 2)

        db.commit()
        AccountService.recalculate_account_balance(db, acc.id)
        db.refresh(acc)

        ws_id = acc.workspace_id
        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(ws_id)
        except Exception:
            pass

        return acc

    @staticmethod
    def set_account_balance(db: Session, account_id: int, target_current_balance: float) -> Optional[Account]:
        """
        Ajusta o saldo atual de uma conta para o valor exato desejado pelo usuário,
        calibrando o saldo inicial necessário para que a equação (inicial + entradas - saídas)
        resulte exatamente no saldo atual informado.
        """
        acc = db.query(Account).filter(Account.id == account_id).first()
        if not acc:
            return None

        inc = float(db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
            Transaction.account_id == acc.id,
            Transaction.type == "income"
        ).scalar() or 0.0)

        exp = float(db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
            Transaction.account_id == acc.id,
            Transaction.type == "expense"
        ).scalar() or 0.0)

        acc.initial_balance = round(target_current_balance - inc + exp, 2)
        acc.current_balance = round(target_current_balance, 2)

        db.commit()
        db.refresh(acc)

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(acc.workspace_id)
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
        """Localiza uma conta pelo nome ou apelido (ex: 'caixa', 'bb', 'santander', 'nubank')"""
        if not name:
            return None
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

        # 1. Match exato prioritário
        for acc in accounts:
            acc_name_lower = acc.name.lower().strip()
            if acc_name_lower == target:
                return acc

        # 2. Substring (somente se target tiver pelo menos 3 caracteres para evitar falsos positivos)
        if len(target) >= 3:
            for acc in accounts:
                acc_name_lower = acc.name.lower().strip()
                if target in acc_name_lower or acc_name_lower in target:
                    return acc

        return None

    @staticmethod
    def set_transaction_account(db: Session, transaction_id: int, account_id: int) -> Optional[Transaction]:
        """Vincula uma transação a uma conta específica e recalcula os saldos com precisão"""
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        acc = db.query(Account).filter(Account.id == account_id).first()
        if not tx or not acc:
            return None

        old_acc_id = tx.account_id

        # Atualiza a conta na transação
        tx.account_id = acc.id
        tx.payment_method = acc.name
        db.commit()
        db.refresh(tx)

        # Recalcula saldos reais
        if old_acc_id and old_acc_id != acc.id:
            AccountService.recalculate_account_balance(db, old_acc_id)
        AccountService.recalculate_account_balance(db, acc.id)

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(tx.workspace_id)
        except Exception:
            pass

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
        db.commit()

        # Recalcula saldos reais
        AccountService.recalculate_account_balance(db, from_acc.id)
        AccountService.recalculate_account_balance(db, to_acc.id)

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
    def zero_account(
        db: Session,
        workspace_id: int,
        account_id: int,
        year: Optional[int] = None,
        month: Optional[int] = None
    ) -> Dict[str, Any]:
        """Zera o saldo e as movimentações de uma conta bancária específica no mês selecionado"""
        acc = db.query(Account).filter(Account.id == account_id, Account.workspace_id == workspace_id).first()
        if not acc:
            return {"success": False, "message": "Conta não encontrada."}

        now = datetime.datetime.utcnow()
        target_year = year or now.year
        target_month = month or now.month

        # Busca e exclui transações vinculadas a esta conta no mês selecionado
        tx_query = db.query(Transaction).filter(
            Transaction.workspace_id == workspace_id,
            Transaction.account_id == acc.id,
            extract("year", Transaction.transaction_date) == target_year,
            extract("month", Transaction.transaction_date) == target_month
        )
        deleted_count = tx_query.count()
        tx_query.delete(synchronize_session=False)

        db.commit()
        db.expire_all()

        # Recalcula saldo da conta
        AccountService.recalculate_account_balance(db, acc.id)
        db.refresh(acc)

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(workspace_id)
        except Exception:
            pass

        return {
            "success": True,
            "account": acc,
            "deleted_count": deleted_count,
            "year": target_year,
            "month": target_month,
            "message": f"Conta {acc.icon} {acc.name} zerada com sucesso em {target_month:02d}/{target_year}! ({deleted_count} lançamentos removidos)"
        }

    @staticmethod
    def zero_monthly_transactions(
        db: Session,
        workspace_id: int,
        year: Optional[int] = None,
        month: Optional[int] = None
    ) -> Dict[str, Any]:
        """Zera todos os lançamentos financeiros do mês selecionado em todo o workspace"""
        now = datetime.datetime.utcnow()
        target_year = year or now.year
        target_month = month or now.month

        tx_query = db.query(Transaction).filter(
            Transaction.workspace_id == workspace_id,
            extract("year", Transaction.transaction_date) == target_year,
            extract("month", Transaction.transaction_date) == target_month
        )
        deleted_count = tx_query.count()
        tx_query.delete(synchronize_session=False)

        db.commit()
        db.expire_all()

        # Recalcula os saldos de todas as contas
        AccountService.recalculate_account_balances(db, workspace_id)

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(workspace_id)
        except Exception:
            pass

        return {
            "success": True,
            "deleted_count": deleted_count,
            "year": target_year,
            "month": target_month,
            "message": f"Todos os lançamentos de {target_month:02d}/{target_year} foram zerados com sucesso! ({deleted_count} registros excluídos)"
        }
