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
    get_account_filter_keyboard,
    get_expenses_by_account_keyboard,
    get_main_reply_keyboard
)
from app.bot.handlers.auth_helper import get_authenticated_bot_user
from app.utils import format_currency_br, format_number_br
from app.services.account_service import AccountService

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

async def senha_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /senha <nova_senha> para definir ou alterar senha do Painel Web e assistente"""
    user_tg = update.effective_user
    args = context.args or []
    
    # Exclui a mensagem enviada pelo usuário para proteger a privacidade da senha
    try:
        if update.message:
            await update.message.delete()
    except Exception:
        pass

    db = SessionLocal()
    try:
        from app.services.finance_service import FinanceService
        from app.services.user_service import UserService
        from app.config import settings

        user, ws = FinanceService.get_or_create_user(
            db, 
            str(user_tg.id), 
            name=user_tg.full_name or user_tg.first_name, 
            username=user_tg.username
        )

        if not args:
            web_url = f"{settings.BASE_URL}/login"
            await update.effective_chat.send_message(
                "🔑 *Configuração de Senha de Acesso Web*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 *Seu Usuário de Acesso:* `@{user.username or user.telegram_id}`\n"
                f"🌐 *Link do Painel:* {web_url}\n\n"
                "Para definir ou alterar sua senha para o Painel Web, envie:\n"
                "`/senha SuaNovaSenha`\n\n"
                "_(Exemplo: `/senha MinhaSenha123`)_",
                parse_mode="Markdown"
            )
            return

        new_password = " ".join(args).strip()
        if len(new_password) < 4:
            await update.effective_chat.send_message(
                "⚠️ *A senha deve conter no mínimo 4 caracteres.* Envie novamente: `/senha sua_senha`",
                parse_mode="Markdown"
            )
            return

        UserService.change_user_password(db, user.id, new_password)
        user.is_telegram_authenticated = True
        db.commit()

        web_url = f"{settings.BASE_URL}/login"
        msg = (
            "✅ *Senha Cadastrada com Sucesso!*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Usuário:* `@{user.username or user.telegram_id}`\n"
            f"🔑 *Senha:* `{new_password}`\n"
            f"🌐 *Acesse o Painel Web:* {web_url}\n\n"
            "💡 _Utilize o mesmo usuário e senha para logar na tela web do sistema!_"
        )
        await update.effective_chat.send_message(msg, parse_mode="Markdown")
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
    """Comando /extrato [conta] [despesas/receitas] ou botão Últimos Gastos"""
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

        args = context.args or []
        target_type = "all"
        target_acc = None

        if args:
            args_str = " ".join(args).lower()
            if any(w in args_str for w in ["despesa", "despesas", "gasto", "gastos", "saida", "saidas"]):
                target_type = "expense"
            elif any(w in args_str for w in ["receita", "receitas", "entrada", "entradas", "ganho", "ganhos"]):
                target_type = "income"

            for word in args:
                clean_word = word.lower().strip()
                if clean_word not in ["despesa", "despesas", "gasto", "gastos", "receita", "receitas", "todas", "tudo", "extrato"]:
                    acc = AccountService.find_account_by_name(db, ws.id, clean_word)
                    if acc:
                        target_acc = acc
                        break

        tx_type_param = None if target_type == "all" else target_type
        acc_id_param = target_acc.id if target_acc else None

        txs = FinanceService.get_filtered_transactions(
            db=db,
            workspace_id=ws.id,
            tx_type=tx_type_param,
            account_id=acc_id_param,
            limit=8
        )

        acc_name = f" - {target_acc.icon} {target_acc.name}" if target_acc else ""
        type_badge = " (🔴 Só Despesas)" if target_type == "expense" else (" (🟢 Só Receitas)" if target_type == "income" else "")
        title = f"📑 *Extrato: {ws.name}{acc_name}{type_badge}*"

        if not txs:
            empty_msg = f"{title}\n───────────────────\n📭 Nenhuma movimentação encontrada para os filtros selecionados."
            await update.message.reply_text(
                empty_msg,
                parse_mode="Markdown",
                reply_markup=get_extrato_keyboard(txs=[], current_type=target_type, current_acc_id=acc_id_param)
            )
            return

        msg = f"{title}\n───────────────────\n"
        for t in txs:
            icon = "🟢 +" if t.type == "income" else "🔴 -"
            cat = t.category.name if t.category else "Outros"
            dt = t.transaction_date.strftime("%d/%m")
            items_badge = f" • 🛒 {t.items_count} itens" if t.items_count > 0 else ""
            acc_label = t.account.name if t.account else t.payment_method
            msg += f"{icon} *{format_currency_br(t.amount)}* | {t.description}{items_badge}\n   🏷️ _{cat}_ • 💳 _{acc_label}_ • 📅 _{dt}_\n\n"

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_extrato_keyboard(txs=txs, current_type=target_type, current_acc_id=acc_id_param)
        )
    finally:
        db.close()

async def despesas_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /despesas ou /gastos para listar despesas do mês e agrupamento por contas"""
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

        args = context.args or []
        target_acc = None
        if args:
            acc_name_query = " ".join(args).strip()
            target_acc = AccountService.find_account_by_name(db, ws.id, acc_name_query)

        if target_acc:
            stats = FinanceService.get_account_monthly_stats(db, ws.id, target_acc.id)
            txs = FinanceService.get_filtered_transactions(db, ws.id, tx_type="expense", account_id=target_acc.id, limit=8)

            msg = (
                f"🔴 *Despesas do Mês - {target_acc.icon} {target_acc.name}*\n"
                f"📍 *Contexto:* `{ws.name}`\n"
                f"───────────────────\n"
                f"💸 *Total Gasto no Mês:* {format_currency_br(stats.get('total_expense', 0))}\n"
                f"💰 *Saldo Atual da Conta:* {format_currency_br(target_acc.current_balance)}\n"
                f"📊 *Total de Despesas:* {len(txs)} lançamentos\n"
                f"───────────────────\n\n"
            )
            if not txs:
                msg += "📭 _Nenhuma despesa registrada nesta conta no mês atual._"
            else:
                msg += "*Últimos Gastos Registrados:*\n"
                for t in txs:
                    cat = t.category.name if t.category else "Outros"
                    dt = t.transaction_date.strftime("%d/%m")
                    items_badge = f" • 🛒 {t.items_count} itens" if t.items_count > 0 else ""
                    msg += f"🔴 *{format_currency_br(t.amount)}* | {t.description}{items_badge}\n   🏷️ _{cat}_ • 📅 _{dt}_\n\n"

            await update.message.reply_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_extrato_keyboard(txs=txs, current_type="expense", current_acc_id=target_acc.id)
            )
            return

        summary = FinanceService.get_expenses_by_account_summary(db, ws.id)
        txs = FinanceService.get_filtered_transactions(db, ws.id, tx_type="expense", limit=6)

        msg = (
            f"🔴 *Despesas do Mês & Por Conta*\n"
            f"📍 *Contexto:* `{ws.name}`\n"
            f"───────────────────\n"
            f"💸 *Total Geral de Despesas:* {format_currency_br(summary['total_expense'])}\n"
            f"───────────────────\n"
            f"🏦 *Detalhamento por Conta Bancária:*\n"
        )

        for acc_info in summary["accounts"]:
            if acc_info["expense_total"] > 0 or acc_info.get("account_id") is not None:
                icon = acc_info.get("icon", "💳")
                name = acc_info["name"]
                spent = format_currency_br(acc_info["expense_total"])
                pct = acc_info["expense_percentage"]
                bal = format_currency_br(acc_info["current_balance"])
                msg += f"{icon} *{name}:* {spent} ({pct:.0f}%) • _Saldo: {bal}_\n"

        msg += f"───────────────────\n"
        if txs:
            msg += f"\n👇 *Últimos Gastos Registrados:*\n"
            for t in txs:
                cat = t.category.name if t.category else "Outros"
                dt = t.transaction_date.strftime("%d/%m")
                acc_label = t.account.name if t.account else t.payment_method
                items_badge = f" • 🛒 {t.items_count} itens" if t.items_count > 0 else ""
                msg += f"🔴 *{format_currency_br(t.amount)}* | {t.description}{items_badge}\n   🏷️ _{cat}_ • 💳 _{acc_label}_ • 📅 _{dt}_\n\n"

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_expenses_by_account_keyboard(summary["accounts"])
        )
    finally:
        db.close()

async def receitas_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /receitas ou /entradas para listar receitas do mês e por conta"""
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

        args = context.args or []
        target_acc = None
        if args:
            acc_name_query = " ".join(args).strip()
            target_acc = AccountService.find_account_by_name(db, ws.id, acc_name_query)

        if target_acc:
            stats = FinanceService.get_account_monthly_stats(db, ws.id, target_acc.id)
            txs = FinanceService.get_filtered_transactions(db, ws.id, tx_type="income", account_id=target_acc.id, limit=8)

            msg = (
                f"🟢 *Receitas do Mês - {target_acc.icon} {target_acc.name}*\n"
                f"📍 *Contexto:* `{ws.name}`\n"
                f"───────────────────\n"
                f"💰 *Total Recebido no Mês:* {format_currency_br(stats.get('total_income', 0))}\n"
                f"🏦 *Saldo Atual da Conta:* {format_currency_br(target_acc.current_balance)}\n"
                f"📊 *Total de Entradas:* {len(txs)} lançamentos\n"
                f"───────────────────\n\n"
            )
            if not txs:
                msg += "📭 _Nenhuma receita registrada nesta conta no mês atual._"
            else:
                msg += "*Últimas Receitas Registradas:*\n"
                for t in txs:
                    cat = t.category.name if t.category else "Receita"
                    dt = t.transaction_date.strftime("%d/%m")
                    msg += f"🟢 *{format_currency_br(t.amount)}* | {t.description}\n   🏷️ _{cat}_ • 📅 _{dt}_\n\n"

            await update.message.reply_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_extrato_keyboard(txs=txs, current_type="income", current_acc_id=target_acc.id)
            )
            return

        summary = FinanceService.get_monthly_summary(db, ws.id)
        txs = FinanceService.get_filtered_transactions(db, ws.id, tx_type="income", limit=8)

        msg = (
            f"🟢 *Receitas do Mês*\n"
            f"📍 *Contexto:* `{ws.name}`\n"
            f"───────────────────\n"
            f"💰 *Total de Receitas:* {format_currency_br(summary['total_income'])}\n"
            f"───────────────────\n\n"
        )
        if not txs:
            msg += "📭 _Nenhuma receita registrada neste perfil no mês atual._"
        else:
            msg += "*Últimas Receitas Registradas:*\n"
            for t in txs:
                cat = t.category.name if t.category else "Receita"
                dt = t.transaction_date.strftime("%d/%m")
                acc_label = t.account.name if t.account else t.payment_method
                msg += f"🟢 *{format_currency_br(t.amount)}* | {t.description}\n   🏷️ _{cat}_ • 💳 _{acc_label}_ • 📅 _{dt}_\n\n"

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_extrato_keyboard(txs=txs, current_type="income", current_acc_id=None)
        )
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

async def cupom_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /cupom, /cupons, /itens, /notafiscal para visualizar itens de compras e cupons fiscais"""
    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

        from app.models import Transaction
        from app.bot.keyboards import get_cupom_detail_keyboard, get_cupons_list_keyboard
        from app.utils import format_full_receipt_text

        # Busca transações com itens do workspace
        tx_query = db.query(Transaction).filter(
            Transaction.workspace_id == ws.id
        ).order_by(Transaction.transaction_date.desc(), Transaction.id.desc())

        all_txs = tx_query.all()
        recent_with_items = [t for t in all_txs if t.items and len(t.items) > 0]

        if not recent_with_items:
            msg = (
                f"🧾 *Cupons Fiscais & Itens ({ws.name})*\n\n"
                f"📭 Nenhum cupom fiscal ou compra com itens detalhados foi encontrado neste perfil.\n\n"
                f"💡 *Como cadastrar itens:*\n"
                f"• Envie a foto ou PDF do cupom fiscal / nota fiscal\n"
                f"• Ou envie por texto/áudio: `Gastei 150 no Angeloni: arroz 25, feijão 10, carne 80, café 35`\n"
                f"• Os produtos ficam salvos e você poderá consultá-los a qualquer momento!"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        args = context.args or []
        target_tx = None

        if args:
            search_term = " ".join(args).strip().lower()
            if search_term.isdigit():
                tx_id_arg = int(search_term)
                target_tx = next((t for t in recent_with_items if t.id == tx_id_arg), None)

            if not target_tx:
                for t in recent_with_items:
                    if search_term in (t.description or "").lower():
                        target_tx = t
                        break
                    if any(search_term in (it.name or "").lower() for it in t.items):
                        target_tx = t
                        break

        # Se não especificou ou não achou busca exata, usa o mais recente
        if not target_tx:
            target_tx = recent_with_items[0]

        items = FinanceService.get_transaction_items(db, target_tx.id)

        idx = recent_with_items.index(target_tx) if target_tx in recent_with_items else 0
        prev_id = recent_with_items[idx + 1].id if idx + 1 < len(recent_with_items) else None
        next_id = recent_with_items[idx - 1].id if idx > 0 else None

        receipt_text = format_full_receipt_text(target_tx, items)
        reply_markup = get_cupom_detail_keyboard(target_tx.id, prev_id=prev_id, next_id=next_id)

        await update.message.reply_text(
            receipt_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    finally:
        db.close()


async def versao_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /versao ou /sobre para exibir a versão instalada do sistema"""
    from app.version import get_version_info
    v = get_version_info()
    user_tg = update.effective_user
    msg = (
        f"🚀 *{v['app_name']}*\n\n"
        f"📌 *Versão da Aplicação:* `{v['version_tag']}`\n"
        f"🏷️ *Commit GitHub:* `{v['commit']}`\n"
        f"📅 *Data do Release:* `{v['release_date']}`\n"
        f"🌐 *Ambiente:* `Produção (Porta 8085)`\n"
        f"⚡ *Motor IA:* `Gemini 3.5 Flash Lite (Multimodal)`\n\n"
        f"✨ _Sistema 100% atualizado e sincronizado em tempo real com o Painel Web._"
    )
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=get_dashboard_link_keyboard(str(user_tg.id) if user_tg else "")
    )

