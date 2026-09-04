from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from app.database import SessionLocal
from app.services.finance_service import FinanceService
from app.services.reminder_service import ReminderService
from app.services.goal_service import GoalService
from app.services.vehicle_service import VehicleService
from app.services.shopping_service import ShoppingService
from app.bot.keyboards import get_profile_inline_keyboard, get_dashboard_link_keyboard, get_reminder_action_keyboard, get_extrato_keyboard
from app.utils import format_currency_br, format_number_br

async def saldo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /saldo ou botão Saldo do Mês"""
    user_tg = update.effective_user
    db = SessionLocal()
    try:
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id), user_tg.full_name, user_tg.username)
        summary = FinanceService.get_monthly_summary(db, ws.id)

        cat_lines = ""
        for c in summary["category_breakdown"][:5]:
            pct = (c["total"] / summary["total_expense"] * 100) if summary["total_expense"] > 0 else 0
            cat_lines += f"{c['icon']} *{c['name']}:* {format_currency_br(c['total'])} ({pct:.0f}%)\n"

        saldo_emoji = "🟢" if summary["net_balance"] >= 0 else "🔴"

        msg = (
            f"📊 *Resumo Financeiro - {summary['month']:02d}/{summary['year']}*\n"
            f"📍 *Contexto:* `{ws.name}`\n"
            f"───────────────────\n"
            f"🟢 *Receitas:* {format_currency_br(summary['total_income'])}\n"
            f"🔴 *Despesas:* {format_currency_br(summary['total_expense'])}\n"
            f"{saldo_emoji} *Saldo Líquido:* {format_currency_br(summary['net_balance'])}\n"
            f"───────────────────\n"
            f"💡 *Saúde Financeira:* {summary['health_status']} ({summary['health_score']}/100)\n\n"
        )

        if cat_lines:
            msg += f"🏆 *Top Categorias de Gastos:*\n{cat_lines}\n"
        
        msg += f"_{summary['transaction_count']} movimentações registradas neste mês._"

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_dashboard_link_keyboard(str(user_tg.id))
        )
    finally:
        db.close()

async def extrato_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /extrato ou botão Últimos Gastos"""
    user_tg = update.effective_user
    db = SessionLocal()
    try:
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id))
        from app.models import Transaction
        txs = db.query(Transaction).filter(Transaction.workspace_id == ws.id).order_by(Transaction.transaction_date.desc()).limit(8).all()

        if not txs:
            await update.message.reply_text("📭 Nenhuma movimentação registrada recentemente neste perfil.")
            return

        msg = f"📑 *Últimos Lançamentos - {ws.name}:*\n───────────────────\n"
        for t in txs:
            icon = "🟢 +" if t.type == "income" else "🔴 -"
            cat = t.category.name if t.category else "Outros"
            dt = t.transaction_date.strftime("%d/%m")
            msg += f"{icon} *{format_currency_br(t.amount)}* | {t.description}\n   🏷️ _{cat}_ • 💳 _{t.payment_method}_ • 📅 _{dt}_\n\n"

        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_extrato_keyboard())
    finally:
        db.close()

async def perfil_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /perfil para alternar PF / PJ / Família"""
    user_tg = update.effective_user
    db = SessionLocal()
    try:
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id))
        msg = (
            f"👤 *Gestão de Perfis & Contas*\n\n"
            f"Atualmente você está lançando em:\n"
            f"👉 *{ws.name}* (Tipo: `{ws.type.upper()}`)\n\n"
            f"🔑 Código de Convite deste workspace: `{ws.invite_code}`\n\n"
            f"Selecione abaixo para qual perfil deseja alternar:"
        )
        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_profile_inline_keyboard(ws.type)
        )
    finally:
        db.close()

async def lembretes_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /lembretes para ver contas a pagar/receber"""
    user_tg = update.effective_user
    db = SessionLocal()
    try:
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id))
        reminders = ReminderService.get_upcoming_reminders(db, ws.id)

        if not reminders:
            msg = (
                f"⏰ *Contas e Lembretes - {ws.name}*\n\n"
                f"✅ Você não tem nenhuma conta pendente para os próximos 30 dias!\n\n"
                f"💡 _Para cadastrar: Envie 'Lembrar de pagar luz 150 dia 10'_"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        msg = f"⏰ *Contas e Vencimentos Pendentes ({ws.name}):*\n───────────────────\n"
        for r in reminders:
            tipo_icon = "🔴 Pagar" if r.type == "to_pay" else "🟢 Receber"
            due_str = r.due_date.strftime("%d/%m/%Y")
            msg += f"{tipo_icon}: *{r.title}* - {format_currency_br(r.amount)}\n📅 Vence em: *{due_str}*\n\n"

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_reminder_action_keyboard(reminders[0].id)
        )
    finally:
        db.close()

async def metas_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /metas para ver objetivos financeiros"""
    user_tg = update.effective_user
    db = SessionLocal()
    try:
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id))
        from app.models import Goal
        goals = db.query(Goal).filter(Goal.workspace_id == ws.id).all()

        if not goals:
            msg = (
                f"🎯 *Metas e Caixinhas Financeiras*\n\n"
                f"Você ainda não criou nenhuma meta.\n\n"
                f"💡 _Exemplo de comando: 'Nova meta: Viagem 3000' ou 'Guardei 150 pra viagem'_"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        msg = f"🎯 *Minhas Metas & Caixinhas ({ws.name}):*\n───────────────────\n"
        for g in goals:
            bar = GoalService.get_progress_bar(g.progress_percentage)
            check = "✅ " if g.is_completed else ""
            msg += (
                f"{check}{g.icon} *{g.title}*\n"
                f"💰 {format_currency_br(g.current_amount)} / {format_currency_br(g.target_amount)}\n"
                f"📊 `{bar}`\n\n"
            )

        await update.message.reply_text(msg, parse_mode="Markdown")
    finally:
        db.close()

async def veiculo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /veiculo para controle veicular"""
    user_tg = update.effective_user
    db = SessionLocal()
    try:
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id))
        vehicle = VehicleService.get_or_create_vehicle(db, ws.id)
        summary = VehicleService.get_vehicle_summary(db, vehicle.id)

        msg = (
            f"🚗 *Módulo de Veículos & Manutenção*\n"
            f"🚘 *Veículo:* {vehicle.name} ({vehicle.plate or 'Sem Placa'})\n"
            f"📟 *KM Atual:* {format_number_br(vehicle.current_km)} km\n"
            f"💰 *Total Gasto em Manutenções:* {format_currency_br(summary['total_spent'])}\n"
        )

        if summary.get("oil_alert"):
            msg += f"\n{summary['oil_alert']}\n"
        elif summary.get("last_oil_change"):
            loc = summary["last_oil_change"]
            msg += f"\n🛢️ *Última troca de óleo:* {format_number_br(loc.km)} km (Próxima: {format_number_br(loc.next_due_km)} km)\n"

        msg += f"\n💡 _Para lançar: Envie 'Troquei óleo 200 km 50000' ou 'Abasteci 150 km 50300'_"

        await update.message.reply_text(msg, parse_mode="Markdown")
    finally:
        db.close()

async def mercado_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /mercado para lista de compras"""
    user_tg = update.effective_user
    db = SessionLocal()
    try:
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id))
        s_list = ShoppingService.get_or_create_active_list(db, ws.id)

        if not s_list.items:
            msg = (
                f"🛒 *Lista de Mercado ({s_list.title})*\n\n"
                f"Sua lista está vazia no momento!\n\n"
                f"💡 _Adicione itens enviando: 'Colocar arroz 2kg, feijao e cafe na lista'_"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        msg = f"🛒 *Lista de Mercado: {s_list.title}*\n───────────────────\n"
        buttons = []
        for item in s_list.items:
            status_icon = "☑️" if item.is_checked else "⬜"
            preco_str = f" (~{format_currency_br(item.estimated_price)})" if item.estimated_price > 0 else ""
            msg += f"{status_icon} {item.name} ({item.quantity:.0f} {item.unit}){preco_str}\n"
            buttons.append([InlineKeyboardButton(f"{status_icon} {item.name}", callback_data=f"toggle_item_{item.id}")])

        buttons.append([InlineKeyboardButton("🏁 Finalizar Compra e Gerar Despesa", callback_data=f"checkout_list_{s_list.id}")])

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    finally:
        db.close()

async def painel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /painel para abrir o dashboard web"""
    user_tg = update.effective_user
    msg = (
        f"🌐 *Painel Web & Dashboard Interativo*\n\n"
        f"Acesse gráficos analíticos detalhados, fluxo de caixa diário, filtros avançados e exportação de planilhas!"
    )
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=get_dashboard_link_keyboard(str(user_tg.id))
    )

async def contas_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /contas ou botão Minhas Contas"""
    user_tg = update.effective_user
    db = SessionLocal()
    try:
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id))
        from app.services.account_service import AccountService
        from app.bot.keyboards import get_manage_accounts_keyboard
        accounts = AccountService.get_accounts(db, ws.id)

        total_saldo = sum(acc.current_balance for acc in accounts)
        msg = (
            f"💳 *Minhas Contas e Carteiras ({ws.name})*\n"
            f"💰 *Saldo Consolidado:* {format_currency_br(total_saldo)}\n"
            f"───────────────────\n\n"
        )
        for acc in accounts:
            msg += f"{acc.icon} *{acc.name}:* {format_currency_br(acc.current_balance)}\n"

        msg += f"\n💡 _Para lançar direto em uma conta: 'Gastei 50 no mercado no Santander' ou clique nos botões após o lançamento._"

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_manage_accounts_keyboard(accounts)
        )
    finally:
        db.close()

async def entrar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /entrar <codigo> para ingressar em um grupo/workspace compartilhado"""
    user_tg = update.effective_user
    db = SessionLocal()
    try:
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id), user_tg.full_name, user_tg.username)
        if not context.args or len(context.args) == 0:
            await update.message.reply_text(
                "ℹ️ *Como ingressar em um grupo/workspace:*\n\n"
                "Digite `/entrar <CODIGO_DO_CONVITE>`\n"
                "Exemplo: `/entrar ABCD1234`\n\n"
                "Ou clique no link direto de convite enviado pelo administrador do grupo.",
                parse_mode="Markdown"
            )
            return

        code = context.args[0].replace("convite_", "").replace("join_", "").strip().upper()
        target_ws = FinanceService.join_shared_workspace(db, user, code)
        if target_ws:
            await update.message.reply_text(
                f"🎉 *Sucesso!* Você agora faz parte do grupo/perfil: *{target_ws.name}*!\n\n"
                f"A partir de agora, suas mensagens de gastos e receitas serão registradas neste perfil.",
                parse_mode="Markdown",
                reply_markup=get_profile_inline_keyboard(target_ws.type)
            )
        else:
            await update.message.reply_text(
                f"❌ Código de convite `{code}` não encontrado ou inválido. Verifique com o administrador.",
                parse_mode="Markdown"
            )
    finally:
        db.close()

