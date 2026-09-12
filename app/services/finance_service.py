import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_
from app.models import User, Workspace, WorkspaceMember, Category, Transaction, TransactionItem

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
    def _are_descriptions_matching(desc1: str, desc2: str) -> bool:
        """
        Verifica se os fornecedores / estabelecimentos são os mesmos ou muito similares.
        """
        d1 = desc1.lower().strip()
        d2 = desc2.lower().strip()
        if not d1 or not d2:
            return False
        if d1 == d2:
            return True
        if d1 in d2 or d2 in d1:
            return True

        # Stop words ignoradas na comparação
        stop_words = {"de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "para", "com", "e", "ou", "por", "um", "uma", "compra", "gasto", "pagamento", "valor", "cupom", "nota", "fiscal"}
        words1 = set(w for w in d1.split() if len(w) >= 3 and w not in stop_words)
        words2 = set(w for w in d2.split() if len(w) >= 3 and w not in stop_words)

        if words1 and words2 and (words1 & words2):
            return True

        return False

    @staticmethod
    def _are_items_duplicate(existing_items: List[TransactionItem], new_items: List[Any]) -> bool:
        """
        Compara duas listas de itens para determinar se são a mesma compra / cupom fiscal.
        Retorna True se forem substancialmente os mesmos itens, ou False se forem compras com produtos diferentes.
        """
        if not existing_items or not new_items:
            # Se um dos lados não tem itens discriminados, não é possível diferenciar por itens
            return True

        def normalize_name(n: str) -> str:
            return "".join(c for c in n.lower() if c.isalnum() or c.isspace()).strip()

        existing_names = [normalize_name(it.name) for it in existing_items if it.name]
        new_names = []
        for it in new_items:
            if hasattr(it, "name") and it.name:
                new_names.append(normalize_name(it.name))
            elif isinstance(it, dict) and it.get("name"):
                new_names.append(normalize_name(str(it["name"])))

        if not existing_names or not new_names:
            return True

        # Se a contagem de itens for muito discrepante (ex: um tem 8 itens e o outro tem 1), são compras distintas
        min_len = min(len(existing_names), len(new_names))
        max_len = max(len(existing_names), len(new_names))
        if max_len > 1 and (min_len / max_len) < 0.4:
            return False

        # Verifica interseção de nomes ou palavras-chave
        match_count = 0
        for n_name in new_names:
            n_words = set(w for w in n_name.split() if len(w) > 2)
            matched = False
            for e_name in existing_names:
                if n_name == e_name or (len(n_name) > 3 and n_name in e_name) or (len(e_name) > 3 and e_name in n_name):
                    match_count += 1
                    matched = True
                    break
                e_words = set(w for w in e_name.split() if len(w) > 2)
                if n_words and e_words and (n_words & e_words):
                    match_count += 1
                    matched = True
                    break

        similarity = match_count / max(len(new_names), 1)
        # Se 50% ou mais dos itens coincidirem, consideramos a mesma lista de produtos
        return similarity >= 0.5

    @staticmethod
    def find_duplicate_transaction(
        db: Session,
        workspace_id: int,
        type: str,
        amount: float,
        description: str,
        transaction_date: Optional[datetime.datetime] = None,
        hours_window: int = 48,
        items: Optional[List[Any]] = None
    ) -> Optional[Transaction]:
        """
        Verifica se já existe uma transação idêntica no workspace
        (mesmo tipo, mesmo valor, mesmo fornecedor/estabelecimento e mesmos itens se fornecidos).
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
        ).order_by(Transaction.transaction_date.desc()).all()

        for tx in recent_txs:
            if abs(tx.amount - abs(float(amount))) < 0.01:
                # Checa se o fornecedor / estabelecimento corresponde
                if FinanceService._are_descriptions_matching(description, tx.description):
                    # Se fornecedor e valor batem, checa os itens caso ambos tenham itens
                    existing_items = tx.items or []
                    if items and existing_items:
                        if FinanceService._are_items_duplicate(existing_items, items):
                            return tx
                        else:
                            # Itens são comprovadamente diferentes! Não é duplicidade.
                            continue
                    else:
                        # Se não há itens para comparar em um deles, mas fornecedor e valor batem na janela
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
        receipt_url: Optional[str] = None,
        items: Optional[List[Any]] = None
    ) -> Transaction:
        """Registra uma nova transação financeira vinculando à categoria, conta bancária e itens detalhados se houver"""
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
        db.flush()

        # Adiciona itens detalhados se fornecidos (item a item)
        if items:
            for item in items:
                # Trata item seja objeto Pydantic ou dict
                if hasattr(item, "model_dump"):
                    item_data = item.model_dump()
                elif isinstance(item, dict):
                    item_data = item
                else:
                    item_data = {
                        "name": getattr(item, "name", str(item)),
                        "quantity": getattr(item, "quantity", 1.0),
                        "unit": getattr(item, "unit", "un"),
                        "unit_price": getattr(item, "unit_price", 0.0),
                        "total_price": getattr(item, "total_price", 0.0),
                        "category": getattr(item, "category", "Geral")
                    }

                name = str(item_data.get("name", "")).strip()
                if not name:
                    continue
                
                qty = float(item_data.get("quantity", 1.0) or 1.0)
                unit_p = float(item_data.get("unit_price", 0.0) or 0.0)
                tot_p = float(item_data.get("total_price", 0.0) or 0.0)
                if tot_p == 0.0 and unit_p > 0.0:
                    tot_p = round(qty * unit_p, 2)
                elif unit_p == 0.0 and tot_p > 0.0 and qty > 0:
                    unit_p = round(tot_p / qty, 2)

                tx_item = TransactionItem(
                    transaction_id=tx.id,
                    name=name,
                    quantity=qty,
                    unit=str(item_data.get("unit", "un") or "un"),
                    unit_price=unit_p,
                    total_price=tot_p,
                    category=str(item_data.get("category", "Geral") or "Geral")
                )
                db.add(tx_item)

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

    @staticmethod
    def get_transaction_items(db: Session, transaction_id: int) -> List[TransactionItem]:
        """Recupera a lista de itens/produtos de uma transação"""
        return db.query(TransactionItem).filter(TransactionItem.transaction_id == transaction_id).order_by(TransactionItem.id.asc()).all()

    @staticmethod
    def save_transaction_items(db: Session, transaction_id: int, items_data: List[Dict[str, Any]]) -> List[TransactionItem]:
        """Sobrescreve/salva os itens de uma transação"""
        # Remove itens anteriores
        db.query(TransactionItem).filter(TransactionItem.transaction_id == transaction_id).delete()
        created_items = []

        for item in items_data:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            qty = float(item.get("quantity", 1.0) or 1.0)
            unit_p = float(item.get("unit_price", 0.0) or 0.0)
            tot_p = float(item.get("total_price", 0.0) or 0.0)
            if tot_p == 0.0 and unit_p > 0.0:
                tot_p = round(qty * unit_p, 2)
            elif unit_p == 0.0 and tot_p > 0.0 and qty > 0:
                unit_p = round(tot_p / qty, 2)

            t_item = TransactionItem(
                transaction_id=transaction_id,
                name=name,
                quantity=qty,
                unit=str(item.get("unit", "un") or "un"),
                unit_price=unit_p,
                total_price=tot_p,
                category=str(item.get("category", "Geral") or "Geral")
            )
            db.add(t_item)
            created_items.append(t_item)

        db.commit()
        return created_items

    @staticmethod
    def delete_transaction_items(db: Session, transaction_id: int) -> bool:
        """Remove o detalhamento item a item de uma transação mantendo a transação com o valor total"""
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx:
            return False
        db.query(TransactionItem).filter(TransactionItem.transaction_id == transaction_id).delete()
        db.commit()
        try:
            from app.services.event_bus import event_bus
            event_bus.notify_workspace_update(tx.workspace_id)
        except Exception:
            pass
        return True

    @staticmethod
    def get_items_analytics(db: Session, workspace_id: int, year: Optional[int] = None, month: Optional[int] = None) -> Dict[str, Any]:
        """
        Calcula estatísticas detalhadas de itens comprados no workspace/período.
        Permite analisar o que foi comprado: top produtos por gasto e quantidade, gastos por categoria de produto, ticket médio.
        """
        now = datetime.datetime.now()
        target_year = int(year) if year else now.year
        target_month = int(month) if month else now.month

        # Busca todas as transações com itens do período
        query = db.query(TransactionItem, Transaction).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).filter(
            Transaction.workspace_id == workspace_id,
            extract('year', Transaction.transaction_date) == target_year,
            extract('month', Transaction.transaction_date) == target_month
        )

        results = query.all()

        total_items_count = len(results)
        total_spent_on_items = 0.0
        total_units_sum = 0.0

        item_aggregated: Dict[str, Dict[str, Any]] = {}
        category_aggregated: Dict[str, Dict[str, Any]] = {}
        recent_item_purchases: List[Dict[str, Any]] = []

        for item, tx in results:
            price = item.total_price or (item.unit_price * item.quantity)
            total_spent_on_items += price
            total_units_sum += item.quantity

            # Agregação por nome normalizado de produto
            norm_name = item.name.strip().title()
            if norm_name not in item_aggregated:
                item_aggregated[norm_name] = {
                    "name": norm_name,
                    "total_spent": 0.0,
                    "total_quantity": 0.0,
                    "unit": item.unit or "un",
                    "purchase_count": 0,
                    "avg_price": 0.0,
                    "last_unit_price": item.unit_price or 0.0,
                    "category": item.category or "Geral"
                }
            item_aggregated[norm_name]["total_spent"] += price
            item_aggregated[norm_name]["total_quantity"] += item.quantity
            item_aggregated[norm_name]["purchase_count"] += 1
            if item.unit_price > 0:
                item_aggregated[norm_name]["last_unit_price"] = item.unit_price

            # Agregação por categoria de produto
            cat_name = item.category or "Geral"
            if cat_name not in category_aggregated:
                category_aggregated[cat_name] = {
                    "category": cat_name,
                    "total_spent": 0.0,
                    "items_count": 0,
                    "items": {}
                }
            category_aggregated[cat_name]["total_spent"] += price
            category_aggregated[cat_name]["items_count"] += 1
            if norm_name not in category_aggregated[cat_name]["items"]:
                category_aggregated[cat_name]["items"][norm_name] = {
                    "name": norm_name,
                    "total_spent": 0.0,
                    "total_quantity": 0.0,
                    "unit": item.unit or "un"
                }
            category_aggregated[cat_name]["items"][norm_name]["total_spent"] += price
            category_aggregated[cat_name]["items"][norm_name]["total_quantity"] += item.quantity

            recent_item_purchases.append({
                "id": item.id,
                "transaction_id": tx.id,
                "transaction_desc": tx.description,
                "transaction_date": tx.transaction_date.strftime("%d/%m/%Y"),
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit,
                "unit_price": item.unit_price,
                "total_price": price,
                "category": item.category
            })

        # Calcula preços médios
        for k, v in item_aggregated.items():
            if v["total_quantity"] > 0:
                v["avg_price"] = round(v["total_spent"] / v["total_quantity"], 2)
            v["total_spent"] = round(v["total_spent"], 2)
            v["total_quantity"] = round(v["total_quantity"], 2)

        # Top itens por maior valor total gasto
        top_by_spent = sorted(item_aggregated.values(), key=lambda x: x["total_spent"], reverse=True)[:10]

        # Top itens mais frequentes / comprados
        top_by_quantity = sorted(item_aggregated.values(), key=lambda x: (x["purchase_count"], x["total_quantity"]), reverse=True)[:10]

        # Categorias de produtos ordenadas
        categories_list = []
        for cat in sorted(category_aggregated.values(), key=lambda x: x["total_spent"], reverse=True):
            items_arr = sorted(cat["items"].values(), key=lambda x: x["total_spent"], reverse=True)
            for it in items_arr:
                it["total_spent"] = round(it["total_spent"], 2)
                it["total_quantity"] = round(it["total_quantity"], 2)
            categories_list.append({
                "category": cat["category"],
                "total_spent": round(cat["total_spent"], 2),
                "items_count": cat["items_count"],
                "items_list": items_arr
            })

        return {
            "workspace_id": workspace_id,
            "year": target_year,
            "month": target_month,
            "total_items_count": total_items_count,
            "total_spent_on_items": round(total_spent_on_items, 2),
            "total_units_sum": round(total_units_sum, 2),
            "top_by_spent": top_by_spent,
            "top_by_quantity": top_by_quantity,
            "categories": categories_list,
            "recent_items": recent_item_purchases[:30]
        }


