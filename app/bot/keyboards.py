from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Optional, Any
from app.config import settings
from app.models import Account

from app.utils import format_currency_br

def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Teclado de acesso rápido na barra inferior do Telegram"""
    keyboard = [
        [KeyboardButton("📊 Saldo do Mês"), KeyboardButton("📑 Últimos Gastos")],
        [KeyboardButton("💳 Minhas Contas / Bancos"), KeyboardButton("👤/🏢 Alternar Perfil")],
        [KeyboardButton("⏰ Contas a Vencer"), KeyboardButton("🎯 Minhas Metas")],
        [KeyboardButton("🛒 Lista de Mercado"), KeyboardButton("🚗 Manutenção Veículo")],
        [KeyboardButton("🌐 Abrir Painel Web")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_profile_inline_keyboard(current_type: str) -> InlineKeyboardMarkup:
    """Teclado inline para alternar entre PF, PJ e Família"""
    btn_pf = "✅ 👤 Pessoal (PF)" if current_type == "personal" else "👤 Pessoal (PF)"
    btn_pj = "✅ 🏢 Empresa (PJ)" if current_type == "business" else "🏢 Empresa (PJ)"
    btn_fam = "✅ 👨‍👩‍👧‍👦 Família" if current_type == "family" else "👨‍👩‍👧‍👦 Família / Sócios"

    keyboard = [
        [InlineKeyboardButton(btn_pf, callback_data="switch_pf"),
         InlineKeyboardButton(btn_pj, callback_data="switch_pj")],
        [InlineKeyboardButton(btn_fam, callback_data="switch_family")],
        [InlineKeyboardButton("🔗 Código de Convite / Entrar em Grupo", callback_data="show_invite")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_accounts_selection_keyboard(transaction_id: int, accounts: List[Account], current_account_id: Optional[int] = None, has_items: bool = False, items_count: int = 0) -> InlineKeyboardMarkup:
    """Gera botões interativos para vincular a transação a uma conta bancária com 1 clique e gerenciar itens"""
    buttons = []
    row = []
    # Apenas contas ativas
    active_accounts = [a for a in accounts if a.is_active != False]
    for acc in active_accounts:
        check = "✅ " if acc.id == current_account_id else ""
        btn_text = f"{check}{acc.icon} {acc.name}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"txacc_{transaction_id}_{acc.id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if has_items and items_count > 0:
        buttons.append([
            InlineKeyboardButton(f"🧾 Ver Lista Completa ({items_count} itens)", callback_data=f"txitems_{transaction_id}"),
            InlineKeyboardButton("💰 Manter Só Total", callback_data=f"txdelitems_{transaction_id}")
        ])

    buttons.append([
        InlineKeyboardButton("⚙️ Gerenciar Contas", callback_data="manage_accounts"),
        InlineKeyboardButton("🗑️ Cancelar Lançamento", callback_data=f"del_tx_{transaction_id}")
    ])
    return InlineKeyboardMarkup(buttons)

def get_duplicate_confirmation_keyboard(token: str) -> InlineKeyboardMarkup:
    """Gera botões Sim / Não para confirmação de lançamento em duplicidade"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Sim, Cadastrar", callback_data=f"dup_confirm_{token}"),
            InlineKeyboardButton("❌ Não, Cancelar", callback_data=f"dup_cancel_{token}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_extrato_keyboard(
    txs: Optional[List[Any]] = None,
    current_type: str = "all",
    current_acc_id: Optional[int] = None
) -> InlineKeyboardMarkup:
    """Teclado de ações para a mensagem de extrato com filtros por tipo (receitas/despesas/todas), por conta bancária e cupons"""
    keyboard = []
    acc_param = current_acc_id if current_acc_id is not None else 0

    # Linha 1: Filtros de Tipo (Todas / Despesas / Receitas)
    all_label = "✅ 🔄 Todas" if current_type == "all" else "🔄 Todas"
    exp_label = "✅ 🔴 Despesas" if current_type == "expense" else "🔴 Despesas"
    inc_label = "✅ 🟢 Receitas" if current_type == "income" else "🟢 Receitas"

    keyboard.append([
        InlineKeyboardButton(all_label, callback_data=f"filter_tx_{acc_param}_all"),
        InlineKeyboardButton(exp_label, callback_data=f"filter_tx_{acc_param}_expense"),
        InlineKeyboardButton(inc_label, callback_data=f"filter_tx_{acc_param}_income")
    ])

    # Linha 2: Filtro por Conta Bancária & Relatório de Gastos por Conta
    keyboard.append([
        InlineKeyboardButton("🔍 Filtrar por Conta", callback_data=f"filter_acc_menu_{current_type}"),
        InlineKeyboardButton("📊 Despesas por Conta", callback_data="expenses_by_account")
    ])

    has_any_items = False
    if txs:
        for t in txs:
            c = getattr(t, "items_count", 0)
            if c > 0:
                has_any_items = True
                short_desc = t.description[:16] if t.description else "Cupom"
                keyboard.append([
                    InlineKeyboardButton(f"🧾 Ver Itens: {short_desc} ({c})", callback_data=f"txitems_{t.id}")
                ])
                if len(keyboard) >= 5:
                    break

    if has_any_items:
        keyboard.append([
            InlineKeyboardButton("🧾 Meus Cupons Fiscais", callback_data="list_cupons")
        ])

    keyboard.append([
        InlineKeyboardButton("✏️ Editar Lançamento", callback_data="manage_edit_tx"),
        InlineKeyboardButton("🗑️ Excluir", callback_data="manage_del_tx")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_account_filter_keyboard(accounts: List[Account], current_type: str = "all", current_acc_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Menu para selecionar conta bancária para filtrar lançamentos"""
    buttons = []
    all_acc_label = "✅ 🏦 Todas as Contas (Sem Filtro)" if (current_acc_id is None or current_acc_id == 0) else "🏦 Todas as Contas (Sem Filtro)"
    buttons.append([InlineKeyboardButton(all_acc_label, callback_data=f"filter_tx_0_{current_type}")])

    active = [a for a in accounts if a.is_active != False]
    for acc in active:
        check = "✅ " if (current_acc_id == acc.id) else ""
        btn_text = f"{check}{acc.icon} {acc.name} ({format_currency_br(acc.current_balance)})"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"filter_tx_{acc.id}_{current_type}")])

    buttons.append([
        InlineKeyboardButton("🔙 Voltar ao Extrato", callback_data=f"filter_tx_{current_acc_id or 0}_{current_type}")
    ])
    return InlineKeyboardMarkup(buttons)

def get_expenses_by_account_keyboard(accounts_data: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Botões de atalho para explorar despesas de contas específicas"""
    buttons = []
    for acc in accounts_data[:6]:
        acc_id = acc.get("account_id")
        if acc_id is not None and acc.get("expense_total", 0) > 0:
            name = acc.get("name", "Conta")
            buttons.append([
                InlineKeyboardButton(f"🔍 Ver Despesas: {acc.get('icon', '💳')} {name}", callback_data=f"filter_tx_{acc_id}_expense")
            ])

    buttons.append([
        InlineKeyboardButton("🔴 Todas as Despesas do Mês", callback_data="filter_tx_0_expense"),
        InlineKeyboardButton("🟢 Todas as Receitas do Mês", callback_data="filter_tx_0_income")
    ])
    buttons.append([
        InlineKeyboardButton("📑 Voltar ao Extrato Completo", callback_data="back_to_extrato")
    ])
    return InlineKeyboardMarkup(buttons)

def get_cupons_list_keyboard(tx_with_items: List[Any]) -> InlineKeyboardMarkup:
    """Gera botões para selecionar qual cupom fiscal / compra detalhada deseja visualizar"""
    buttons = []
    for t in tx_with_items[:8]:
        c = getattr(t, "items_count", 0) or (len(t.items) if getattr(t, "items", None) else 0)
        dt_str = t.transaction_date.strftime("%d/%m") if getattr(t, "transaction_date", None) else ""
        short_desc = t.description[:14] if t.description else "Cupom"
        btn_text = f"🧾 {short_desc} ({c} itens) • {format_currency_br(t.amount)} [{dt_str}]"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"txitems_{t.id}")])

    buttons.append([
        InlineKeyboardButton("📑 Voltar ao Extrato", callback_data="back_to_extrato")
    ])
    return InlineKeyboardMarkup(buttons)

def get_cupom_detail_keyboard(tx_id: int, prev_id: Optional[int] = None, next_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Teclado de ações para a visualização detalhada de um cupom fiscal"""
    buttons = []
    
    # Navegação entre cupons (se houver anterior/próximo)
    nav_row = []
    if prev_id:
        nav_row.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"txitems_{prev_id}"))
    if next_id:
        nav_row.append(InlineKeyboardButton("Próximo ➡️", callback_data=f"txitems_{next_id}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("🧾 Todos os Cupons", callback_data="list_cupons"),
        InlineKeyboardButton("✏️ Editar Lançamento", callback_data=f"menu_edit_tx_{tx_id}")
    ])
    buttons.append([
        InlineKeyboardButton("💳 Alterar Conta", callback_data=f"txaccmenu_{tx_id}"),
        InlineKeyboardButton("💰 Manter Só Total", callback_data=f"txdelitems_{tx_id}")
    ])
    buttons.append([
        InlineKeyboardButton("📑 Voltar ao Extrato", callback_data="back_to_extrato")
    ])
    return InlineKeyboardMarkup(buttons)

def get_edit_transactions_keyboard(txs) -> InlineKeyboardMarkup:
    """Gera botões para selecionar qual lançamento recente deseja editar"""
    buttons = []
    for t in txs:
        icon = "🟢" if t.type == "income" else "🔴"
        items_badge = f" (🛒 {t.items_count})" if getattr(t, "items_count", 0) > 0 else ""
        label = f"✏️ {icon} {t.description[:16]}{items_badge} ({format_currency_br(t.amount)})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"menu_edit_tx_{t.id}")])
    buttons.append([InlineKeyboardButton("🔙 Voltar ao Extrato", callback_data="back_to_extrato")])
    return InlineKeyboardMarkup(buttons)

def get_transaction_edit_options_keyboard(tx_id: int, has_items: bool = False, items_count: int = 0) -> InlineKeyboardMarkup:
    """Menu de opções de edição de um lançamento específico"""
    keyboard = []
    if has_items or items_count > 0:
        keyboard.append([
            InlineKeyboardButton(f"🧾 Ver Itens do Cupom ({items_count} itens)", callback_data=f"txitems_{tx_id}")
        ])

    keyboard.extend([
        [
            InlineKeyboardButton("💰 Alterar Valor", callback_data=f"prompt_tx_amount_{tx_id}"),
            InlineKeyboardButton("📅 Alterar Data", callback_data=f"menu_tx_date_{tx_id}")
        ],
        [
            InlineKeyboardButton("🏷️ Alterar Categoria", callback_data=f"prompt_tx_cat_{tx_id}"),
            InlineKeyboardButton("📝 Alterar Descrição", callback_data=f"prompt_tx_desc_{tx_id}")
        ],
        [
            InlineKeyboardButton("💳 Alterar Conta / Cartão", callback_data=f"txaccmenu_{tx_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Excluir Lançamento", callback_data=f"del_tx_{tx_id}")
        ],
        [
            InlineKeyboardButton("🔙 Voltar à Lista", callback_data="manage_edit_tx")
        ]
    ])
    return InlineKeyboardMarkup(keyboard)

def get_transaction_date_options_keyboard(tx_id: int) -> InlineKeyboardMarkup:
    """Opções rápidas para alterar data de um lançamento efetivado"""
    keyboard = [
        [
            InlineKeyboardButton("📅 Hoje", callback_data=f"set_tx_date_{tx_id}_today"),
            InlineKeyboardButton("📅 Ontem", callback_data=f"set_tx_date_{tx_id}_yesterday")
        ],
        [
            InlineKeyboardButton("📅 Anteontem", callback_data=f"set_tx_date_{tx_id}_2days"),
            InlineKeyboardButton("✏️ Digitar Data (DD/MM)", callback_data=f"prompt_tx_date_{tx_id}")
        ],
        [
            InlineKeyboardButton("🔙 Voltar", callback_data=f"menu_edit_tx_{tx_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_delete_transactions_keyboard(txs) -> InlineKeyboardMarkup:
    """Gera botões para exclusão rápida de lançamentos recentes"""
    buttons = []
    for t in txs:
        icon = "🟢" if t.type == "income" else "🔴"
        label = f"❌ {icon} {t.description[:18]} ({format_currency_br(t.amount)})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"del_tx_{t.id}")])
    buttons.append([InlineKeyboardButton("🔙 Voltar ao Extrato", callback_data="back_to_extrato")])
    return InlineKeyboardMarkup(buttons)

def get_manage_accounts_keyboard(accounts: List[Account]) -> InlineKeyboardMarkup:
    """Menu para gerenciar e cadastrar novas contas"""
    buttons = []
    for acc in accounts:
        status_icon = "🟢" if (acc.is_active != False) else "⏸️ (Inativa)"
        btn_text = f"{acc.icon} {acc.name} {status_icon} • {format_currency_br(acc.current_balance)}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"view_acc_{acc.id}")])

    buttons.append([
        InlineKeyboardButton("🔄 Transferir Entre Contas", callback_data="transfer_start"),
        InlineKeyboardButton("➕ Nova Conta", callback_data="add_account_prompt")
    ])
    buttons.append([
        InlineKeyboardButton("🔄 Recalcular Saldos", callback_data="recalc_balances")
    ])
    return InlineKeyboardMarkup(buttons)

def get_transfer_origin_keyboard(accounts: List[Account]) -> InlineKeyboardMarkup:
    """Seleção de conta de origem para transferência"""
    buttons = []
    active = [a for a in accounts if a.is_active != False]
    for acc in active:
        btn_text = f"📤 {acc.icon} {acc.name} ({format_currency_br(acc.current_balance)})"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"transfer_from_{acc.id}")])
    buttons.append([InlineKeyboardButton("🔙 Cancelar / Voltar", callback_data="manage_accounts")])
    return InlineKeyboardMarkup(buttons)

def get_transfer_dest_keyboard(accounts: List[Account], origin_id: int) -> InlineKeyboardMarkup:
    """Seleção de conta de destino para transferência"""
    buttons = []
    active = [a for a in accounts if a.is_active != False and a.id != origin_id]
    for acc in active:
        btn_text = f"📥 {acc.icon} {acc.name} ({format_currency_br(acc.current_balance)})"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"transfer_to_{origin_id}_{acc.id}")])
    buttons.append([InlineKeyboardButton("🔙 Cancelar / Voltar", callback_data="transfer_start")])
    return InlineKeyboardMarkup(buttons)

def get_account_detail_keyboard(account: Account) -> InlineKeyboardMarkup:
    """Teclado de controle e ações para uma conta bancária específica"""
    toggle_text = "⏸️ Inativar Conta" if (account.is_active != False) else "▶️ Reativar Conta"
    buttons = [
        [
            InlineKeyboardButton("🔴 Só Despesas", callback_data=f"filter_tx_{account.id}_expense"),
            InlineKeyboardButton("🟢 Só Receitas", callback_data=f"filter_tx_{account.id}_income")
        ],
        [
            InlineKeyboardButton("📑 Extrato Completo Desta Conta", callback_data=f"filter_tx_{account.id}_all")
        ],
        [
            InlineKeyboardButton("💰 Ajustar Saldo / Saldo Inicial", callback_data=f"prompt_set_bal_{account.id}"),
            InlineKeyboardButton("🔄 Transferir", callback_data=f"transfer_from_{account.id}")
        ],
        [
            InlineKeyboardButton("🧹 Zerar Lançamentos (Mês)", callback_data=f"prompt_zero_acc_{account.id}")
        ],
        [
            InlineKeyboardButton(toggle_text, callback_data=f"toggle_acc_{account.id}"),
            InlineKeyboardButton("🗑️ Excluir Conta", callback_data=f"del_acc_{account.id}")
        ],
        [
            InlineKeyboardButton("🔙 Voltar para Minhas Contas", callback_data="manage_accounts")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def get_zero_account_confirmation_keyboard(account_id: int) -> InlineKeyboardMarkup:
    """Confirmação de zeramento de conta"""
    keyboard = [
        [InlineKeyboardButton("⚠️ Sim, Zerar Lançamentos do Mês", callback_data=f"confirm_zero_acc_{account_id}")],
        [InlineKeyboardButton("❌ Cancelar / Voltar", callback_data=f"view_acc_{account_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_zero_selection_keyboard(accounts: List[Account]) -> InlineKeyboardMarkup:
    """Menu para o usuário escolher qual conta zerar ou se deseja zerar todo o mês"""
    buttons = []
    for acc in accounts:
        btn_text = f"🧹 Zerar {acc.icon} {acc.name} ({format_currency_br(acc.current_balance)})"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"prompt_zero_acc_{acc.id}")])

    buttons.append([
        InlineKeyboardButton("💥 Zerar TODOS os Gastos do Mês Atual", callback_data="prompt_zero_all_month")
    ])
    buttons.append([
        InlineKeyboardButton("❌ Cancelar", callback_data="close_message")
    ])
    return InlineKeyboardMarkup(buttons)

def get_zero_all_month_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Confirmação para zerar todos os lançamentos do mês"""
    keyboard = [
        [InlineKeyboardButton("⚠️ Sim, Zerar TODOS os Gastos do Mês", callback_data="confirm_zero_all_month")],
        [InlineKeyboardButton("❌ Cancelar / Não Zerar", callback_data="close_message")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_quick_add_accounts_keyboard() -> InlineKeyboardMarkup:
    """Botões de criação rápida de contas mais populares"""
    buttons = [
        [InlineKeyboardButton("🟣 + Nubank", callback_data="quick_add_nubank"),
         InlineKeyboardButton("🟠 + Inter", callback_data="quick_add_inter")],
        [InlineKeyboardButton("🔴 + Santander", callback_data="quick_add_santander"),
         InlineKeyboardButton("🔵 + Caixa", callback_data="quick_add_caixa")],
        [InlineKeyboardButton("🟡 + Banco do Brasil", callback_data="quick_add_bb"),
         InlineKeyboardButton("🟠 + Itaú", callback_data="quick_add_itau")],
        [InlineKeyboardButton("💵 + Dinheiro / Carteira", callback_data="quick_add_dinheiro"),
         InlineKeyboardButton("⚫ + C6 Bank", callback_data="quick_add_c6")],
        [InlineKeyboardButton("🔙 Voltar para Minhas Contas", callback_data="manage_accounts")]
    ]
    return InlineKeyboardMarkup(buttons)



def get_dashboard_link_keyboard(telegram_id: str) -> InlineKeyboardMarkup:
    """Botões de ações e relatórios rápidos"""
    keyboard = [
        [InlineKeyboardButton("🌐 Link do Dashboard Web", callback_data=f"show_web_link_{telegram_id}")],
        [InlineKeyboardButton("📥 Exportar Excel (.xlsx)", callback_data="export_excel"),
         InlineKeyboardButton("📄 Exportar PDF (.pdf)", callback_data="export_pdf")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_reminders_list_keyboard(reminders: list) -> InlineKeyboardMarkup:
    """Gera botões interativos para cada conta/boleto pendente com opções de pagar e alterar vencimento"""
    buttons = []
    for r in reminders:
        due_str = r.due_date.strftime("%d/%m")
        btn_pay = f"💳 Pagar: {r.title[:14]} ({format_currency_br(r.amount)})"
        buttons.append([
            InlineKeyboardButton(btn_pay, callback_data=f"pay_reminder_{r.id}")
        ])
        buttons.append([
            InlineKeyboardButton(f"📅 Vencimento ({due_str})", callback_data=f"edit_due_menu_{r.id}"),
            InlineKeyboardButton("🗑️ Excluir", callback_data=f"delete_reminder_{r.id}")
        ])
    buttons.append([
        InlineKeyboardButton("🔄 Atualizar Agenda", callback_data="refresh_reminders")
    ])
    return InlineKeyboardMarkup(buttons)

def get_reminder_pay_account_keyboard(reminder_id: int, accounts: list) -> InlineKeyboardMarkup:
    """Gera botões com as contas bancárias para escolher de onde debitar o valor"""
    buttons = []
    row = []
    for acc in accounts:
        btn_text = f"{acc.icon} {acc.name} ({format_currency_br(acc.current_balance)})"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"pay_confirm_{reminder_id}_{acc.id}"))
        if len(row) == 1:  # 1 por linha para nomes e saldos ficarem legíveis
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("❌ Cancelar / Voltar", callback_data="refresh_reminders")
    ])
    return InlineKeyboardMarkup(buttons)

def get_reminder_due_date_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    """Opções rápidas e personalizadas para alterar a data de vencimento ou valor de uma conta/boleto"""
    keyboard = [
        [
            InlineKeyboardButton("⏳ +1 Dia", callback_data=f"snooze_days_{reminder_id}_1"),
            InlineKeyboardButton("⏳ +3 Dias", callback_data=f"snooze_days_{reminder_id}_3"),
            InlineKeyboardButton("⏳ +7 Dias", callback_data=f"snooze_days_{reminder_id}_7"),
        ],
        [
            InlineKeyboardButton("⏳ +15 Dias", callback_data=f"snooze_days_{reminder_id}_15"),
            InlineKeyboardButton("⏳ +30 Dias", callback_data=f"snooze_days_{reminder_id}_30"),
        ],
        [
            InlineKeyboardButton("📅 Digitar Nova Data", callback_data=f"prompt_due_date_{reminder_id}"),
            InlineKeyboardButton("💰 Alterar Valor", callback_data=f"prompt_rem_amount_{reminder_id}")
        ],
        [
            InlineKeyboardButton("🔙 Voltar para Agenda", callback_data="refresh_reminders")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_reminder_action_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✅ Marcar como Pago", callback_data=f"pay_reminder_{reminder_id}")],
        [InlineKeyboardButton("📅 Alterar Vencimento", callback_data=f"edit_due_menu_{reminder_id}"),
         InlineKeyboardButton("🗑️ Excluir", callback_data=f"delete_reminder_{reminder_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


