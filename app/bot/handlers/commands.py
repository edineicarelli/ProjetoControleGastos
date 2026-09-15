import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from app.database import SessionLocal
from app.services.finance_service import FinanceService
from app.services.reminder_service import ReminderService
from app.services.goal_service import GoalService
from app.services.vehicle_service import VehicleService
from app.services.shopping_service import ShoppingService
from app.services.auth_service import AuthService
from app.bot.keyboards import (
    get_profile_inline_keyboard,
    get_dashboard_link_keyboard,
    get_reminder_action_keyboard,
    get_reminders_list_keyboard,
    get_extrato_keyboard,
    get_main_reply_keyboard
)
from app.bot.handlers.auth_helper import get_authenticated_bot_user
from app.utils import format_currency_br, format_number_br

logger = logging.getLogger(__name__)

async def login_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /login <usuario> <senha> ou /login <senha> para autenticação segura"""
    user_tg = update.effective_user
    args = context.args or []

    # Tenta excluir a mensagem para não expor a senha no chat
    try:
        if update.message:
            await update.message.delete()
    except Exception:
        pass

    if not args:
        await update.effective_chat.send_message(
            "🔒 *Instruções de Login no Telegram*\n\n"
            "Envie no formato:\n"
            "`/login seu_usuario sua_senha`\n\n"
            "Ou se sua conta já estiver vinculada ao seu número de telefone, basta enviar:\n"
            "`/login sua_senha` (ou digitar diretamente a senha no chat).\n\n"
            "_(Exemplo: `/login admin MinhaSenha123`)_",
            parse_mode="Markdown"
        )
        return

    username = None
    password = None

    if len(args) == 1:
        password = args[0].strip()
    elif len(args) >= 2:
        username = args[0].strip()
        password = " ".join(args[1:]).strip()

    db = SessionLocal()
    try:
        success, msg, user = AuthService.authenticate_telegram_user(
            db=db,
            telegram_id=str(user_tg.id),
            password=password,
            username=username,
            name=user_tg.full_name or user_tg.first_name
        )

        if success and user:
            reply_msg = (
                f"🎉 *Autenticação Concluída com Sucesso!*\n\n"
                f"Olá, *{user.name or user.username}*! Seu acesso ao assistente financeiro no Telegram está liberado.\n\n"
                f"💡 _Envie uma mensagem de texto, grave um áudio ou use o menu abaixo para começar._"
            )
            await update.effective_chat.send_message(
                reply_msg,
                parse_mode="Markdown",
                reply_markup=get_main_reply_keyboard()
            )
        else:
            await update.effective_chat.send_message(
                f"{msg}\n\n💡 _Dica: Use a senha exata cadastrada no painel Web._",
                parse_mode="Markdown"
            )
    finally:
        db.close()

async def logout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /sair ou /logout para bloquear o acesso do Telegram"""
    user_tg = update.effective_user
    db = SessionLocal()
    try:
        AuthService.logout_telegram_user(db, str(user_tg.id))
        await update.effective_chat.send_message(
            "🔒 *Sessão Bloqueada no Telegram*\n\n"
            "Você encerrou sua sessão com sucesso. Para voltar a utilizar o assistente, digite sua senha de acesso ou envie `/login usuario senha`.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
    finally:
        db.close()

async def saldo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /saldo ou botão Saldo do Mês"""
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

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

        user_tg = update.effective_user
        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_dashboard_link_keyboard(str(user_tg.id))
        )
    finally:
        db.close()

async def extrato_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /extrato ou botão Últimos Gastos"""
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

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
            items_badge = f" • 🛒 {t.items_count} itens" if t.items_count > 0 else ""
            msg += f"{icon} *{format_currency_br(t.amount)}* | {t.description}{items_badge}\n   🏷️ _{cat}_ • 💳 _{t.payment_method}_ • 📅 _{dt}_\n\n"

        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_extrato_keyboard(txs))
    finally:
        db.close()

async def perfil_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /perfil para alternar PF / PJ / Família"""
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

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
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

        reminders = ReminderService.get_upcoming_reminders(db, ws.id)

        if not reminders:
            msg = (
                f"⏰ *Contas e Lembretes - {ws.name}*\n\n"
                f"🎉 Nenhuma conta pendente para os próximos dias!\n"
                f"Todas as contas cadastradas estão em dia.\n\n"
                f"💡 _Para cadastrar uma nova conta: Envie 'Lembrar de pagar luz 150 dia 10' ou envie o PDF do boleto._"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        msg = f"⏰ *Contas e Vencimentos Pendentes ({ws.name}):*\n───────────────────\n\n"
        total_a_pagar = sum(r.amount for r in reminders if r.type == "to_pay")
        
        for r in reminders:
            tipo_icon = "🔴 A Pagar" if r.type == "to_pay" else "🟢 A Receber"
            due_str = r.due_date.strftime("%d/%m/%Y")
            msg += f"📝 *{r.title}*\n💰 Valor: *{format_currency_br(r.amount)}* ({tipo_icon})\n📅 Vencimento: *{due_str}*\n\n"

        if total_a_pagar > 0:
            msg += f"───────────────────\n💵 *Total Pendente a Pagar:* {format_currency_br(total_a_pagar)}\n\n"
        msg += "👇 _Clique no botão abaixo correspondente à conta que deseja marcar como paga:_"

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_reminders_list_keyboard(reminders)
        )
    finally:
        db.close()

async def metas_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /metas para ver objetivos financeiros"""
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

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
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

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
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

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
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

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
    finally:
        db.close()

async def contas_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /contas ou botão Minhas Contas"""
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

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
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

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

async def zerar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /zerar ou /zerarconta para zerar o valor e lançamentos da conta ou do mês"""
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

        from app.services.account_service import AccountService
        from app.bot.keyboards import get_zero_selection_keyboard, get_zero_account_confirmation_keyboard

        accounts = AccountService.get_accounts(db, ws.id, active_only=True)

        # Se passou o nome de uma conta específica como argumento (ex: /zerar nubank)
        if context.args and len(context.args) > 0:
            target_name = " ".join(context.args).strip()
            acc = AccountService.find_account_by_name(db, ws.id, target_name)
            if acc:
                msg = (
                    f"⚠️ *Confirmação de Zeramento*\n\n"
                    f"Deseja realmente zerar todos os lançamentos da conta *{acc.icon} {acc.name}* no mês atual?\n\n"
                    f"💰 *Saldo Atual:* {format_currency_br(acc.current_balance)}\n"
                    f"📌 As transações desta conta no mês atual serão removidas e o saldo recalculado."
                )
                await update.message.reply_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=get_zero_account_confirmation_keyboard(acc.id)
                )
                return

        msg = (
            f"🧹 *Zerar Conta / Lançamentos do Mês*\n"
            f"📍 *Contexto:* `{ws.name}`\n\n"
            f"Selecione abaixo qual conta você deseja zerar no mês atual ou escolha zerar todo o extrato mensal:"
        )
        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_zero_selection_keyboard(accounts)
        )
    finally:
        db.close()
