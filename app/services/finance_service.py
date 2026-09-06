import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_
from app.models import User, Workspace, WorkspaceMember, Category, Transaction

DEFAULT_EXPENSE_CATEGORIES = [
    {"name": "Alimentação", "icon": "🍔", "color": "#f59e0b"},
    {"name": "Transporte", "icon": "🚗", "color": "#3b82f6"},
    {"name": "Moradia", "icon": "🏠", "color": "#10b981"},
    {"name": "Saúde", "icon": "💊", "color": "#ef4444"},
    {"name": "Lazer", "icon": "🎉", "color": "#8b5cf6"},
    {"name": "Educação", "icon": "📚", "color": "#06b6d4"},
    {"name": "Compras", "icon": "🛍️", "color": "#ec4899"},
    {"name": "Contas & Serviços", "icon": "📄", "color": "#64748b"},
    {"name": "Outros", "icon": "🏷️", "color": "#94a3b8"},
]

DEFAULT_INCOME_CATEGORIES = [
    {"name": "Salário", "icon": "💰", "color": "#10b981"},
    {"name": "Investimentos", "icon": "📈", "color": "#6366f1"},
    {"name": "Freelas & Extras", "icon": "💻", "color": "#06b6d4"},
    {"name": "Vendas", "icon": "📦", "color": "#f59e0b"},
    {"name": "Outras Receitas", "icon": "💵", "color": "#22c55e"},
]

MONTH_NAMES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

MONTH_SHORT_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}

class FinanceService:
    @staticmethod
    def get_or_create_user(db: Session, telegram_id: str, name: Optional[str] = None, username: Optional[str] = None) -> Tuple[User, Workspace]:
        """Obtém ou cria o usuário do Telegram e inicializa seus workspaces PF e PJ padrões"""
        user = db.query(User).filter(User.telegram_id == str(telegram_id)).first()
        
        # Se não encontrou por telegram_id mas possui username, verifica se foi pré-cadastrado no painel
        if not user and username:
            clean_uname = username.strip().lstrip("@")
            user = db.query(User).filter(User.username.ilike(clean_uname)).first()
            if user:
                user.telegram_id = str(telegram_id)
                if name and (not user.name or user.name == "Novo Usuário"):
                    user.name = name
                db.commit()
                db.refresh(user)

        if not user:
            user = User(
                telegram_id=str(telegram_id),
                name=name or "Usuário",
                username=username.strip().lstrip("@") if username else None
            )
            db.add(user)
            db.flush()

            # Cria Workspace PF
            ws_pf = Workspace(name=f"Pessoal (PF) - {name or 'Usuário'}", type="personal")
            db.add(ws_pf)
            db.flush()
            
            # Adiciona membro
            member_pf = WorkspaceMember(workspace_id=ws_pf.id, user_id=user.id, role="owner")
            db.add(member_pf)

            # Cria Workspace PJ
            ws_pj = Workspace(name=f"Empresa (PJ) - {name or 'Usuário'}", type="business")
            db.add(ws_pj)
            db.flush()

            member_pj = WorkspaceMember(workspace_id=ws_pj.id, user_id=user.id, role="owner")
            db.add(member_pj)

            # Popula categorias e contas iniciais em ambos
            FinanceService._seed_categories(db, ws_pf.id)
            FinanceService._seed_categories(db, ws_pj.id)
            from app.services.account_service import AccountService
            AccountService.seed_default_accounts(db, ws_pf.id)
            AccountService.seed_default_accounts(db, ws_pj.id)

            user.current_workspace_id = ws_pf.id
            db.commit()
            db.refresh(user)
            return user, ws_pf

        if not user.current_workspace:
            # Fallback se não tiver workspace ativo
            first_membership = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user.id).first()
            if first_membership:
                user.current_workspace_id = first_membership.workspace_id
                db.commit()
            else:
                ws_pf = Workspace(name=f"Pessoal (PF) - {user.name}", type="personal")
                db.add(ws_pf)
                db.flush()
                member_pf = WorkspaceMember(workspace_id=ws_pf.id, user_id=user.id, role="owner")
                db.add(member_pf)
                FinanceService._seed_categories(db, ws_pf.id)
                from app.services.account_service import AccountService
                AccountService.seed_default_accounts(db, ws_pf.id)
                user.current_workspace_id = ws_pf.id
                db.commit()

        db.refresh(user)
        return user, user.current_workspace

    @staticmethod
    def _seed_categories(db: Session, workspace_id: int):
        for cat in DEFAULT_EXPENSE_CATEGORIES:
            db.add(Category(
                workspace_id=workspace_id,
                name=cat["name"],
                type="expense",
                icon=cat["icon"],
                color=cat["color"]
            ))
        for cat in DEFAULT_INCOME_CATEGORIES:
            db.add(Category(
                workspace_id=workspace_id,
                name=cat["name"],
                type="income",
                icon=cat["icon"],
                color=cat["color"]
            ))

    @staticmethod
    def switch_workspace(db: Session, user: User, target_type: str) -> Optional[Workspace]:
        """Alterna o workspace atual do usuário entre 'personal', 'business' ou 'family'"""
        memberships = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user.id).all()
        for m in memberships:
            if m.workspace.type == target_type:
                user.current_workspace_id = m.workspace_id
                db.commit()
                db.refresh(user)
                return m.workspace

        # Se não existir ainda o tipo (ex: business), cria sob demanda
        type_name = "Empresa (PJ)" if target_type == "business" else ("Família" if target_type == "family" else "Pessoal (PF)")
        new_ws = Workspace(name=f"{type_name} - {user.name}", type=target_type)
        db.add(new_ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=new_ws.id, user_id=user.id, role="owner"))
        FinanceService._seed_categories(db, new_ws.id)
        from app.services.account_service import AccountService
        AccountService.seed_default_accounts(db, new_ws.id)
        user.current_workspace_id = new_ws.id
        db.commit()
        db.refresh(user)
        return new_ws

    @staticmethod
    def find_duplicate_transaction(
        db: Session,
        workspace_id: int,
        type: str,
        amount: float,
        description: str,
        transaction_date: Optional[datetime.datetime] = None,
        hours_window: int = 24
    ) -> Optional[Transaction]:
        """
        Verifica se já existe uma transação idêntica no workspace
        (mesmo tipo, mesmo valor e dentro de uma janela de tempo no mesmo dia).
        """
        tx_date = transaction_date or datetime.datetime.now()
        start_time = tx_date - datetime.timedelta(hours=hours_window)
        end_time = tx_date + datetime.timedelta(hours=hours_window)

        recent_txs = db.query(Transaction).filter(
            Transaction.workspace_id == workspace_id,
            Transaction.type == type,
            Transaction.status == "completed",
            Transaction.transaction_date >= start_time,
            Transaction.transaction_date <= end_time
        ).all()

        clean_desc = description.lower().strip()
        for tx in recent_txs:
            if abs(tx.amount - abs(float(amount))) < 0.01:
                existing_desc = tx.description.lower().strip()
                if clean_desc == existing_desc:
                    return tx
                # Se ambas tiverem termos coincidentes significativos
                words_new = set(w for w in clean_desc.split() if len(w) > 3)
                words_existing = set(w for w in existing_desc.split() if len(w) > 3)
                if words_new and words_existing and (words_new & words_existing):
                    return tx
                # Se a transação for no mesmo dia e com valor idêntico
                if tx_date.date() == tx.transaction_date.date():
                    return tx

        return None

    @staticmethod
    def add_transaction(
        db: Session,
        workspace_id: int,
        user_id: int,
        type: str,
        amount: float,
        description: str,
        category_name: str = "Outros",
        payment_method: str = "Outro",
        account_id: Optional[int] = None,
        transaction_date: Optional[datetime.datetime] = None,
        receipt_url: Optional[str] = None
    ) -> Transaction:
        """Registra uma nova transação financeira vinculando à categoria e conta bancária adequada"""
        from app.services.account_service import AccountService

        # Busca ou cria categoria
        category = db.query(Category).filter(
            Category.workspace_id == workspace_id,
            Category.name.ilike(category_name.strip())
        ).first()

        if not category:
            icon = "💵" if type == "income" else "🏷️"
            category = Category(
                workspace_id=workspace_id,
                name=category_name.strip().title(),
                type=type,
                icon=icon,
                color="#6366f1"
            )
            db.add(category)
            db.flush()

        # Busca conta se não informada diretamente
        acc = None
        if account_id:
            from app.models import Account
            acc = db.query(Account).filter(Account.id == account_id).first()
        else:
            # Tenta encontrar pelo payment_method ou termos na descrição
            acc = AccountService.find_account_by_name(db, workspace_id, payment_method)
            if not acc:
                for word in ["caixa", "banco do brasil", "bb", "santander", "nubank", "itau", "itaú", "dinheiro"]:
                    if word in description.lower():
                        acc = AccountService.find_account_by_name(db, workspace_id, word)
                        break

        tx = Transaction(
            workspace_id=workspace_id,
            user_id=user_id,
            category_id=category.id,
            account_id=acc.id if acc else None,
            type=type,
            amount=abs(amount),
            description=description.strip(),
            payment_method=acc.name if acc else payment_method,
            transaction_date=transaction_date or datetime.datetime.now(),
            receipt_url=receipt_url,
            status="completed"
        )
        db.add(tx)

        # Atualiza saldo da conta se vinculada
        if acc:
            if type == "income":
                acc.current_balance += abs(amount)
            else:
                acc.current_balance -= abs(amount)

        db.commit()
        db.refresh(tx)

        # Notifica tempo real
        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(workspace_id)
        except Exception:
            pass

        return tx

    @staticmethod
    def get_monthly_summary(db: Session, workspace_id: int, year: Optional[int] = None, month: Optional[int] = None) -> Dict[str, Any]:
        """Calcula o resumo mensal do workspace (Total Entradas, Saídas, Saldo, Categorias) e metadados de navegação de meses"""
        now = datetime.datetime.now()
        target_year = int(year) if year else now.year
        target_month = int(month) if month else now.month

        # Filtra transações do mês selecionado
        txs = db.query(Transaction).filter(
            Transaction.workspace_id == workspace_id,
            extract('year', Transaction.transaction_date) == target_year,
            extract('month', Transaction.transaction_date) == target_month
        ).order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).all()

        total_income = sum(t.amount for t in txs if t.type == "income")
        total_expense = sum(t.amount for t in txs if t.type == "expense")
        net_balance = total_income - total_expense

        # Agrupamento por categoria
        category_totals = {}
        for t in txs:
            if t.type == "expense":
                cat_name = t.category.name if t.category else "Sem Categoria"
                cat_icon = t.category.icon if t.category else "🏷️"
                cat_color = t.category.color if t.category else "#94a3b8"
                if cat_name not in category_totals:
                    category_totals[cat_name] = {"total": 0.0, "icon": cat_icon, "color": cat_color, "count": 0}
                category_totals[cat_name]["total"] += t.amount
                category_totals[cat_name]["count"] += 1

        # Ordenar categorias por maior gasto
        sorted_categories = sorted(
            [{"name": k, **v} for k, v in category_totals.items()],
            key=lambda x: x["total"],
            reverse=True
        )

        # Cálculo de Saúde Financeira Score (0 a 100) e Taxa de Poupança
        if total_income > 0:
            savings_rate = (net_balance / total_income) * 100
            if savings_rate >= 30:
                health_score = min(100, int(90 + (savings_rate - 30) * (10 / 70)))
                health_status = "Excelente 🌟"
            elif savings_rate >= 15:
                health_score = int(75 + (savings_rate - 15) * (14 / 15))
                health_status = "Boa 👍"
            elif savings_rate >= 0:
                health_score = int(55 + (savings_rate / 15) * 19)
                health_status = "Equilibrada ⚖️"
            elif savings_rate >= -30:
                health_score = max(30, int(50 + (savings_rate / 30) * 20))
                health_status = "Atenção (Déficit) ⚠️"
            else:
                health_score = max(10, int(30 + max(-20, (savings_rate + 30) * 0.2)))
                health_status = "Crítico (Alto Déficit) 🚨"
        else:
            if total_expense > 0:
                savings_rate = -100.0
                health_score = 30
                health_status = "Sem Receitas Registradas ⚠️"
            else:
                savings_rate = 0.0
                health_score = 100
                health_status = "Sem Movimentações ⚪"

        # Cálculo de navegação entre meses e anos
        prev_month = 12 if target_month == 1 else target_month - 1
        prev_year = target_year - 1 if target_month == 1 else target_year
        next_month = 1 if target_month == 12 else target_month + 1
        next_year = target_year + 1 if target_month == 12 else target_year

        year_prev = target_year - 1
        year_next = target_year + 1

        month_name = MONTH_NAMES_PT.get(target_month, f"Mês {target_month}")
        month_year_label = f"{month_name} de {target_year}"
        is_current_month = (target_year == now.year and target_month == now.month)

        # Busca meses que houveram movimentações reais no workspace
        db_month_tuples = db.query(
            extract('year', Transaction.transaction_date),
            extract('month', Transaction.transaction_date)
        ).filter(
            Transaction.workspace_id == workspace_id
        ).distinct().all()

        available_pairs = set((int(y), int(m)) for y, m in db_month_tuples if y and m)
        # Sempre inclui o mês selecionado e o mês atual
        available_pairs.add((target_year, target_month))
        available_pairs.add((now.year, now.month))

        # Meses ativos no ano selecionado
        active_months_in_year = sorted(list(set(m for y, m in available_pairs if y == target_year)))
        if not active_months_in_year:
            active_months_in_year = [target_month]

        # Limita a exibição a no máximo 3 meses na tela para não poluir
        if len(active_months_in_year) <= 3:
            visible_months = active_months_in_year
        else:
            if target_month in active_months_in_year:
                idx = active_months_in_year.index(target_month)
                if idx == 0:
                    visible_months = active_months_in_year[:3]
                elif idx == len(active_months_in_year) - 1:
                    visible_months = active_months_in_year[-3:]
                else:
                    visible_months = active_months_in_year[idx - 1 : idx + 2]
            else:
                visible_months = active_months_in_year[:3]

        months_tabs = []
        for m in visible_months:
            months_tabs.append({
                "month": m,
                "year": target_year,
                "short_name": MONTH_SHORT_PT.get(m, str(m)),
                "full_name": MONTH_NAMES_PT.get(m, str(m)),
                "is_selected": (m == target_month),
                "is_current": (m == now.month and target_year == now.year)
            })

        return {
            "year": target_year,
            "month": target_month,
            "year_prev": year_prev,
            "year_next": year_next,
            "month_name": month_name,
            "month_year_label": month_year_label,
            "is_current_month": is_current_month,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "months_tabs": months_tabs,
            "total_income": total_income,
            "total_expense": total_expense,
            "net_balance": net_balance,
            "transaction_count": len(txs),
            "category_breakdown": sorted_categories,
            "savings_rate": round(savings_rate, 1),
            "health_score": health_score,
            "health_status": health_status,
            "monthly_transactions": txs,
            "recent_transactions": txs[:15]
        }

    @staticmethod
    def join_shared_workspace(db: Session, user: User, invite_code: str) -> Optional[Workspace]:
        """Permite que um parceiro/sócio entre na mesma conta compartilhada usando o código de convite"""
        ws = db.query(Workspace).filter(Workspace.invite_code == invite_code.strip().upper()).first()
        if not ws:
            return None

        # Verifica se já é membro
        existing = db.query(WorkspaceMember).filter(
            WorkspaceMember.workspace_id == ws.id,
            WorkspaceMember.user_id == user.id
        ).first()

        if not existing:
            member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="member")
            db.add(member)
        
        user.current_workspace_id = ws.id
        db.commit()
        db.refresh(user)
        return ws

    @staticmethod
    def delete_transaction(db: Session, transaction_id: int) -> bool:
        """Exclui uma transação e estorna o saldo da conta bancária vinculada"""
        from app.models import Transaction
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx:
            return False

        if tx.account:
            if tx.type == "income":
                tx.account.current_balance -= tx.amount
            else:
                tx.account.current_balance += tx.amount

        ws_id = tx.workspace_id
        db.delete(tx)
        db.commit()

        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(ws_id)
        except Exception:
            pass

        return True

    @staticmethod
    def delete_transactions_batch(db: Session, transaction_ids: List[int]) -> int:
        """Exclui múltiplos lançamentos em lote estornando os saldos devidamente"""
        from app.models import Transaction
        if not transaction_ids:
            return 0

        txs = db.query(Transaction).filter(Transaction.id.in_(transaction_ids)).all()
        count = 0
        ws_id = None
        for tx in txs:
            ws_id = tx.workspace_id
            if tx.account:
                if tx.type == "income":
                    tx.account.current_balance -= tx.amount
                else:
                    tx.account.current_balance += tx.amount
            db.delete(tx)
            count += 1

        db.commit()

        if ws_id:
            try:
                from app.services.event_bus import event_bus
                event_bus.notify_workspace_update(ws_id)
            except Exception:
                pass

        return count

