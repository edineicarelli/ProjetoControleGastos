import os
from telegram import Update
from telegram.ext import ContextTypes
from app.database import SessionLocal
from app.services.finance_service import FinanceService
from app.services.reminder_service import ReminderService
from app.services.shopping_service import ShoppingService
from app.services.export_service import ExportService
from app.bot.keyboards import (
    get_profile_inline_keyboard, get_account_detail_keyboard,
    get_quick_add_accounts_keyboard, get_manage_accounts_keyboard,
    get_reminders_list_keyboard, get_reminder_pay_account_keyboard,
    get_reminder_due_date_keyboard, get_extrato_keyboard,
    get_edit_transactions_keyboard, get_transaction_edit_options_keyboard,
    get_transaction_date_options_keyboard, get_delete_transactions_keyboard,
    get_cupons_list_keyboard, get_cupom_detail_keyboard,
    get_account_filter_keyboard, get_expenses_by_account_keyboard,
    get_accounts_selection_keyboard, get_zero_account_confirmation_keyboard,
    get_zero_all_month_confirmation_keyboard, get_dashboard_link_keyboard,
    get_transfer_origin_keyboard, get_transfer_dest_keyboard
)
from app.utils import format_currency_br, format_items_list_text, format_full_receipt_text

from app.bot.handlers.auth_helper import get_authenticated_bot_user

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerencia cliques em botões inline do Telegram com verificação de autenticação"""
    query = update.callback_query
    data = query.data
    user_tg = update.effective_user
    db = SessionLocal()

    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

        await query.answer()

        # 1. Troca de perfis (PF / PJ / Família)
        if data == "switch_pf":
            new_ws = FinanceService.switch_workspace(db, user, "personal")
            await query.edit_message_text(
                f"✅ Perfil alterado para: *{new_ws.name}* (PF)\nSeus lançamentos agora irão para a conta pessoal.",
                parse_mode="Markdown",
                reply_markup=get_profile_inline_keyboard("personal")
            )

        elif data == "switch_pj":
            new_ws = FinanceService.switch_workspace(db, user, "business")
            await query.edit_message_text(
                f"✅ Perfil alterado para: *{new_ws.name}* (PJ)\nSeus lançamentos agora irão para a empresa/PJ.",
                parse_mode="Markdown",
                reply_markup=get_profile_inline_keyboard("business")
            )

        elif data == "switch_family":
            new_ws = FinanceService.switch_workspace(db, user, "family")
            await query.edit_message_text(
                f"✅ Perfil alterado para: *{new_ws.name}* (Família/Compartilhado)\nGastos sincronizados com outros membros.",
                parse_mode="Markdown",
                reply_markup=get_profile_inline_keyboard("family")
            )

        elif data == "show_invite":
            await query.message.reply_text(
                f"🔗 *Código de Convite do Workspace:*\n`{ws.invite_code}`\n\n"
                f"Envie este código para seu parceiro(a) ou sócio. Ao digitar `/entrar {ws.invite_code}` no bot, eles passarão a registrar gastos nesta mesma conta!",
                parse_mode="Markdown"
            )

        # 2. Ações em Lembretes / Contas a Pagar
        elif data.startswith("pay_reminder_"):
            r_id = int(data.split("_")[-1])
            from app.models import Reminder
            rem = db.query(Reminder).filter(Reminder.id == r_id).first()
            if not rem:
                await query.edit_message_text("❌ Conta/lembrete não encontrado ou já excluído.", parse_mode="Markdown")
            elif rem.status == "paid":
                await query.edit_message_text(f"✅ A conta *{rem.title}* já está marcada como PAGA no sistema.", parse_mode="Markdown")
            else:
                from app.services.account_service import AccountService
                accounts = AccountService.get_accounts(db, ws.id, active_only=True)
                if not accounts:
                    AccountService.seed_default_accounts(db, ws.id)
                    accounts = AccountService.get_accounts(db, ws.id, active_only=True)

                tipo_str = "🔴 Conta a Pagar" if rem.type == "to_pay" else "🟢 Conta a Receber"
                msg = (
                    f"💳 *Confirmar Pagamento de Conta*\n\n"
                    f"📝 *{rem.title}*\n"
                    f"💰 *Valor:* {format_currency_br(rem.amount)} ({tipo_str})\n"
                    f"📅 *Vencimento:* {rem.due_date.strftime('%d/%m/%Y')}\n\n"
                    f"👇 *Selecione abaixo de qual conta/banco você debitou este valor:*"
                )
                await query.edit_message_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=get_reminder_pay_account_keyboard(rem.id, accounts)
                )

        elif data.startswith("pay_confirm_"):
            parts = data.split("_")
            rem_id = int(parts[2])
            acc_id = int(parts[3])
            
            from app.models import Account
            acc = db.query(Account).filter(Account.id == acc_id).first()
            rem = ReminderService.mark_as_paid(db, rem_id)
            
            if rem and acc:
                tx = FinanceService.add_transaction(
                    db=db,
                    workspace_id=rem.workspace_id,
                    user_id=user.id,
                    type="expense" if rem.type == "to_pay" else "income",
                    amount=rem.amount,
                    description=f"Pagamento: {rem.title}",
                    category_name="Contas & Serviços",
                    payment_method=acc.name,
                    account_id=acc.id
                )
                db.refresh(acc)
                
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⏰ Ver Outras Contas", callback_data="refresh_reminders"),
                    InlineKeyboardButton("🌐 Abrir Painel Web", callback_data=f"show_web_link_{user_tg.id}")
                ]])
                
                msg = (
                    f"✅ *Conta Paga e Lançada no Extrato!*\n\n"
                    f"📝 *{rem.title}*\n"
                    f"💰 *Valor:* {format_currency_br(rem.amount)}\n"
                    f"🏦 *Debitado de:* {acc.icon} {acc.name}\n"
                    f"💳 *Saldo Atual da Conta:* {format_currency_br(acc.current_balance)}\n"
                    f"📍 *Perfil:* `{ws.name}`\n\n"
                    f"✨ _A conta foi baixada na agenda e o lançamento já atualizou seu extrato e saldo no painel web!_"
                )
                await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=markup)

        elif data == "refresh_reminders":
            reminders = ReminderService.get_upcoming_reminders(db, ws.id)
            if not reminders:
                await query.edit_message_text(
                    f"⏰ *Contas e Lembretes - {ws.name}*\n\n"
                    f"🎉 Nenhuma conta pendente no momento!\nTodas as contas cadastradas estão em dia.",
                    parse_mode="Markdown"
                )
            else:
                msg = f"⏰ *Contas e Vencimentos Pendentes ({ws.name}):*\n───────────────────\n\n"
                total_a_pagar = sum(r.amount for r in reminders if r.type == "to_pay")
                for r in reminders:
                    tipo_icon = "🔴 A Pagar" if r.type == "to_pay" else "🟢 A Receber"
                    due_str = r.due_date.strftime("%d/%m/%Y")
                    msg += f"📝 *{r.title}*\n💰 Valor: *{format_currency_br(r.amount)}* ({tipo_icon})\n📅 Vencimento: *{due_str}*\n\n"
                if total_a_pagar > 0:
                    msg += f"───────────────────\n💵 *Total Pendente a Pagar:* {format_currency_br(total_a_pagar)}\n\n"
                msg += "👇 _Clique no botão abaixo correspondente à conta que deseja marcar como paga:_"
                await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_reminders_list_keyboard(reminders))

        elif data.startswith("edit_due_menu_"):
            r_id = int(data.split("_")[-1])
            from app.models import Reminder
            rem = db.query(Reminder).filter(Reminder.id == r_id).first()
            if not rem:
                await query.edit_message_text("❌ Conta/lembrete não encontrado ou já excluído.", parse_mode="Markdown")
            else:
                tipo_str = "🔴 Conta a Pagar" if rem.type == "to_pay" else "🟢 Conta a Receber"
                msg = (
                    f"📅 *Alterar Data de Vencimento*\n\n"
                    f"📝 *Conta:* {rem.title} ({tipo_str})\n"
                    f"💰 *Valor:* {format_currency_br(rem.amount)}\n"
                    f"🗓️ *Vencimento Atual:* {rem.due_date.strftime('%d/%m/%Y')}\n\n"
                    f"👇 *Selecione uma opção de adiamento ou clique para digitar uma nova data:*"
                )
                await query.edit_message_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=get_reminder_due_date_keyboard(rem.id)
                )

        elif data.startswith("snooze_days_") or data.startswith("snooze_reminder_"):
            parts = data.split("_")
            r_id = int(parts[2])
            days = int(parts[3]) if len(parts) > 3 else 1
            rem = ReminderService.snooze_reminder(db, r_id, days=days)
            if rem:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⏰ Ver Agenda de Contas", callback_data="refresh_reminders"),
                    InlineKeyboardButton("🌐 Abrir Painel Web", callback_data=f"show_web_link_{user_tg.id}")
                ]])
                await query.edit_message_text(
                    f"✅ *Vencimento Atualizado!*\n\n"
                    f"📝 Conta: *{rem.title}*\n"
                    f"⏳ Adiado em: *{days} dia(s)*\n"
                    f"📅 *Novo Vencimento:* *{rem.due_date.strftime('%d/%m/%Y')}*\n\n"
                    f"🔔 Seus alertas foram reprogramados para a nova data automaticamente.",
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            else:
                await query.edit_message_text("❌ Conta não encontrada.", parse_mode="Markdown")

        elif data.startswith("prompt_due_date_"):
            r_id = int(data.split("_")[-1])
            from app.models import Reminder
            rem = db.query(Reminder).filter(Reminder.id == r_id).first()
            if rem:
                context.user_data["waiting_due_date_rem_id"] = rem.id
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Cancelar", callback_data="refresh_reminders")
                ]])
                await query.edit_message_text(
                    f"✏️ *Digitar Nova Data de Vencimento*\n\n"
                    f"📝 Conta: *{rem.title}*\n"
                    f"🗓️ Vencimento atual: *{rem.due_date.strftime('%d/%m/%Y')}*\n\n"
                    f"Envie agora uma mensagem com a nova data no formato `DD/MM` ou `DD/MM/AAAA` (ex: `25/10` ou `15/11/2026`):",
                    parse_mode="Markdown",
                    reply_markup=markup
                )

        elif data.startswith("prompt_rem_amount_"):
            r_id = int(data.split("_")[-1])
            from app.models import Reminder
            rem = db.query(Reminder).filter(Reminder.id == r_id).first()
            if rem:
                context.user_data["waiting_rem_amount_id"] = rem.id
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Cancelar", callback_data="refresh_reminders")
                ]])
                await query.edit_message_text(
                    f"💰 *Alterar Valor da Conta*\n\n"
                    f"📝 Conta: *{rem.title}*\n"
                    f"💵 Valor atual: *{format_currency_br(rem.amount)}*\n\n"
                    f"Envie agora uma mensagem com o novo valor desejado (ex: `150,00` ou `280`):",
                    parse_mode="Markdown",
                    reply_markup=markup
                )

        elif data.startswith("delete_reminder_"):
            r_id = int(data.split("_")[-1])
            from app.models import Reminder
            rem = db.query(Reminder).filter(Reminder.id == r_id).first()
            if rem:
                title = rem.title
                db.delete(rem)
                db.commit()
                await query.edit_message_text(
                    f"🗑️ Lembrete *{title}* excluído com sucesso da sua agenda!",
                    parse_mode="Markdown"
                )

        # 3. Lista de Mercado
        elif data.startswith("toggle_item_"):
            item_id = int(data.split("_")[-1])
            item = ShoppingService.toggle_item(db, item_id)
            if item:
                from app.bot.handlers.commands import mercado_handler
                # Atualiza a lista
                await mercado_handler(update, context)

        elif data.startswith("checkout_list_"):
            list_id = int(data.split("_")[-1])
            s_list = ShoppingService.checkout_list(db, list_id, user.id)
            if s_list:
                await query.edit_message_text(
                    f"🏁 *Compra de Mercado Finalizada!*\n\n"
                    f"💰 Total lançado na categoria Alimentação: *{format_currency_br(s_list.total_spent)}*\n"
                    f"Uma nova lista vazia foi aberta para a próxima compra.",
                    parse_mode="Markdown"
                )

        # 4. Exportações
        elif data == "export_excel":
            filepath = ExportService.export_to_excel(db, ws.id)
            await query.message.reply_document(
                document=open(filepath, "rb"),
                caption=f"📊 Planilha de lançamentos: *{ws.name}*",
                parse_mode="Markdown"
            )

        elif data == "export_pdf":
            filepath = ExportService.export_to_pdf(db, ws.id)
            await query.message.reply_document(
                document=open(filepath, "rb"),
                caption=f"📄 Relatório financeiro em PDF: *{ws.name}*",
                parse_mode="Markdown"
            )

        # 5. Link do Dashboard Web
        elif data.startswith("show_web_link_"):
            from app.config import settings
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            tg_id = data.replace("show_web_link_", "")
            web_url = f"{settings.BASE_URL}/login"
            
            # Telegram API rejeita InlineKeyboardButton com 'localhost' ou '127.0.0.1'
            is_valid_public_url = (
                settings.BASE_URL.startswith("https://") or 
                (settings.BASE_URL.startswith("http://") and not any(loc in settings.BASE_URL for loc in ["localhost", "127.0.0.1", "0.0.0.0"]))
            )
            markup = None
            if is_valid_public_url:
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton(text="🚀 Acessar Painel Web", url=web_url)
                ]])

            user_login_name = user.username or tg_id
            await query.message.reply_text(
                f"🌐 <b>Painel Financeiro Web & Relatórios</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔗 <b>Link de Acesso:</b> {web_url}\n\n"
                f"👤 <b>Seu Usuário:</b> <code>@{user_login_name}</code>\n"
                f"🔑 <b>Senha:</b> Digite <code>/senha SuaSenha</code> no Telegram para definir ou alterar sua senha a qualquer momento.\n\n"
                f"📊 <i>No painel você acompanha gráficos analíticos, fluxo mensal, conciliação bancária e exporta relatórios em Excel/PDF!</i>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # 6. Vínculo de Conta Bancária na Transação
        elif data.startswith("txacc_"):
            parts = data.split("_")
            tx_id = int(parts[1])
            acc_id = int(parts[2])
            from app.services.account_service import AccountService
            tx = AccountService.set_transaction_account(db, tx_id, acc_id)
            if tx and tx.account:
                accounts = AccountService.get_accounts(db, ws.id)
                new_markup = get_accounts_selection_keyboard(
                    tx.id,
                    accounts,
                    tx.account_id,
                    has_items=bool(tx and tx.items_count > 0),
                    items_count=tx.items_count if tx else 0
                )
                try:
                    await query.edit_message_reply_markup(reply_markup=new_markup)
                except Exception:
                    pass
                
                try:
                    await query.message.reply_text(
                        f"💳 <b>Lançamento vinculado com sucesso!</b>\n"
                        f"🏦 Conta: <b>{tx.account.icon} {tx.account.name}</b>\n"
                        f"💰 Saldo atual da conta: <b>{format_currency_br(tx.account.current_balance)}</b>",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

        # 7. Menu de Gerenciar Contas
        elif data == "manage_accounts":
            from app.services.account_service import AccountService
            accounts = AccountService.get_accounts(db, ws.id)
            total_saldo = sum(acc.current_balance for acc in accounts)
            msg = (
                f"💳 *Controle de Contas e Carteiras ({ws.name})*\n"
                f"💰 *Saldo Consolidado:* {format_currency_br(total_saldo)}\n"
                f"───────────────────\n\n"
                f"Clique em uma conta abaixo para ver detalhes, inativar ou excluir:"
            )
            await query.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_manage_accounts_keyboard(accounts)
            )

        elif data.startswith("view_acc_"):
            acc_id = int(data.split("_")[-1])
            from app.models import Account
            acc = db.query(Account).filter(Account.id == acc_id).first()
            if acc:
                status_str = "🟢 Ativa" if (acc.is_active != False) else "⏸️ Inativa"
                stats = FinanceService.get_account_monthly_stats(db, ws.id, acc.id)
                exp_month = stats.get("total_expense", 0.0)
                inc_month = stats.get("total_income", 0.0)
                tx_count = stats.get("transaction_count", len(acc.transactions))
                msg = (
                    f"💳 *Controle da Conta: {acc.icon} {acc.name}*\n"
                    f"───────────────────\n"
                    f"💰 *Saldo Atual:* {format_currency_br(acc.current_balance)}\n"
                    f"🔴 *Despesas no Mês:* {format_currency_br(exp_month)}\n"
                    f"🟢 *Receitas no Mês:* {format_currency_br(inc_month)}\n"
                    f"🏷️ *Saldo Inicial:* {format_currency_br(acc.initial_balance)}\n"
                    f"📑 *Tipo:* `{acc.type.upper()}` • 📌 *Status:* {status_str}\n"
                    f"📊 *Movimentações no Mês:* {tx_count}\n\n"
                    f"Selecione uma ação abaixo:"
                )
                await query.edit_message_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=get_account_detail_keyboard(acc)
                )

        elif data.startswith("toggle_acc_"):
            acc_id = int(data.split("_")[-1])
            from app.services.account_service import AccountService
            acc = AccountService.toggle_account_active(db, acc_id)
            if acc:
                status_str = "🟢 Ativa" if (acc.is_active != False) else "⏸️ Inativa"
                tx_count = len(acc.transactions)
                msg = (
                    f"💳 *Controle da Conta: {acc.icon} {acc.name}*\n"
                    f"───────────────────\n"
                    f"💰 *Saldo Atual:* {format_currency_br(acc.current_balance)}\n"
                    f"🏷️ *Saldo Inicial:* {format_currency_br(acc.initial_balance)}\n"
                    f"📑 *Tipo:* `{acc.type.upper()}`\n"
                    f"📌 *Status:* {status_str}\n"
                    f"📊 *Lançamentos Vinculados:* {tx_count}\n\n"
                    f"✅ *Status alterado com sucesso!*"
                )
                await query.edit_message_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=get_account_detail_keyboard(acc)
                )

        elif data.startswith("del_acc_"):
            acc_id = int(data.split("_")[-1])
            from app.models import Account
            from app.services.account_service import AccountService
            acc = db.query(Account).filter(Account.id == acc_id).first()
            if acc:
                nome = acc.name
                AccountService.delete_account(db, acc.id)
                accounts = AccountService.get_accounts(db, ws.id)
                await query.edit_message_text(
                    f"🗑️ Conta *{nome}* removida!\n\nSuas contas restantes:",
                    parse_mode="Markdown",
                    reply_markup=get_manage_accounts_keyboard(accounts)
                )

        elif data.startswith("prompt_set_bal_"):
            acc_id = int(data.split("_")[-1])
            from app.models import Account
            from app.services.account_service import AccountService
            acc = db.query(Account).filter(Account.id == acc_id).first()
            if acc:
                context.user_data["awaiting_set_acc_bal"] = acc.id
                msg = (
                    f"💰 *Ajustar Saldo da Conta: {acc.icon} {acc.name}*\n\n"
                    f"Saldo Atual Registrado: *{format_currency_br(acc.current_balance)}*\n"
                    f"Saldo Inicial: *{format_currency_br(acc.initial_balance)}*\n\n"
                    f"👇 *Envie uma mensagem com o novo valor desejado:*\n"
                    f"• _Ex: '2500,00' para definir o saldo atual para R$ 2.500,00_\n"
                    f"• _Ex: 'inicial 1000' para alterar o saldo inicial para R$ 1.000,00_"
                )
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data=f"view_acc_{acc.id}")]])
                await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=markup)

        elif data == "recalc_balances":
            from app.services.account_service import AccountService
            AccountService.recalculate_account_balances(db, ws.id)
            accounts = AccountService.get_accounts(db, ws.id)
            total_saldo = sum(acc.current_balance for acc in accounts)
            msg = (
                f"🔄 *Saldos Recalculados com Sucesso!*\n\n"
                f"💳 *Contas e Carteiras ({ws.name})*\n"
                f"💰 *Saldo Consolidado:* {format_currency_br(total_saldo)}\n"
                f"───────────────────\n\n"
                f"Clique em uma conta para ver detalhes:"
            )
            await query.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_manage_accounts_keyboard(accounts)
            )

        # 8. Zeramento de Contas e Mês
        elif data.startswith("prompt_zero_acc_"):
            acc_id = int(data.split("_")[-1])
            from app.models import Account
            acc = db.query(Account).filter(Account.id == acc_id).first()
            if acc:
                msg = (
                    f"⚠️ *Confirmação de Zeramento*\n\n"
                    f"Deseja realmente zerar todos os lançamentos da conta *{acc.icon} {acc.name}* no mês atual?\n\n"
                    f"💰 *Saldo Atual:* {format_currency_br(acc.current_balance)}\n"
                    f"📌 Os lançamentos desta conta no mês atual serão removidos e o saldo recalculado."
                )
                await query.edit_message_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=get_zero_account_confirmation_keyboard(acc.id)
                )

        elif data.startswith("confirm_zero_acc_"):
            acc_id = int(data.split("_")[-1])
            from app.services.account_service import AccountService
            from app.models import Account
            res = AccountService.zero_account(db, ws.id, acc_id)
            if res.get("success"):
                acc = res.get("account")
                msg = (
                    f"🎉 *Conta Zerada com Sucesso!*\n\n"
                    f"🏦 *Conta:* {acc.icon} {acc.name}\n"
                    f"💰 *Novo Saldo:* {format_currency_br(acc.current_balance)}\n"
                    f"🗑️ *Registros Removidos:* {res.get('deleted_count', 0)} no mês {res.get('month'):02d}/{res.get('year')}\n\n"
                    f"Seu extrato e saldo consolidado foram atualizados!"
                )
                await query.edit_message_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=get_account_detail_keyboard(acc)
                )
            else:
                await query.edit_message_text(f"❌ {res.get('message', 'Erro ao zerar conta.')}", parse_mode="Markdown")

        elif data == "prompt_zero_all_month":
            import datetime
            now = datetime.datetime.utcnow()
            msg = (
                f"🚨 *ATENÇÃO: Zerar Mês Atual*\n\n"
                f"Deseja realmente zerar **TODOS OS LANÇAMENTOS** do mês *{now.month:02d}/{now.year}* no perfil *{ws.name}*?\n\n"
                f"⚠️ Todas as receitas e despesas deste mês serão excluídas e os saldos das contas recalculados. Esta ação não poderá ser desfeita!"
            )
            await query.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_zero_all_month_confirmation_keyboard()
            )

        elif data == "confirm_zero_all_month":
            from app.services.account_service import AccountService
            res = AccountService.zero_monthly_transactions(db, ws.id)
            msg = (
                f"💥 *Mês Zerado com Sucesso!*\n\n"
                f"📅 Mês: *{res.get('month'):02d}/{res.get('year')}*\n"
                f"🗑️ Total de registros excluídos: *{res.get('deleted_count', 0)}*\n"
                f"💰 Todos os saldos foram recalculados do zero para este mês."
            )
            await query.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_dashboard_link_keyboard(str(user_tg.id))
            )

        elif data == "close_message":
            try:
                await query.message.delete()
            except Exception:
                await query.edit_message_text("Operação cancelada.")

        elif data == "add_account_prompt":
            msg = (
                f"➕ *Cadastrar Nova Conta Bancária / Carteira*\n\n"
                f"💡 Escolha uma das opções rápidas abaixo ou envie uma mensagem com o nome da sua conta:\n"
                f"• _Ex: 'Criar conta Inter'_\n"
                f"• _Ex: 'Criar conta C6 Bank saldo 1500'_\n"
                f"• _Ex: 'Nova conta Poupança Caixa'_"
            )
            await query.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_quick_add_accounts_keyboard()
            )

        elif data.startswith("quick_add_"):
            preset = data.replace("quick_add_", "")
            from app.services.account_service import AccountService
            presets_map = {
                "nubank": ("Nubank", "checking", "🟣", "#8b5cf6"),
                "inter": ("Banco Inter", "checking", "🟠", "#f97316"),
                "santander": ("Santander", "checking", "🔴", "#ef4444"),
                "caixa": ("Caixa Econômica", "checking", "🔵", "#3b82f6"),
                "bb": ("Banco do Brasil", "checking", "🟡", "#fbbf24"),
                "itau": ("Itaú", "checking", "🟠", "#ea580c"),
                "dinheiro": ("Dinheiro / Carteira", "cash", "💵", "#10b981"),
                "c6": ("C6 Bank", "checking", "⚫", "#374151")
            }
            if preset in presets_map:
                name, acc_type, icon, color = presets_map[preset]
                acc = AccountService.create_account(db, ws.id, name=name, type=acc_type, icon=icon, color=color, initial_balance=0.0)
                accounts = AccountService.get_accounts(db, ws.id)
                await query.edit_message_text(
                    f"✅ Conta *{acc.icon} {acc.name}* cadastrada com sucesso!\n\nSuas contas atualizadas:",
                    parse_mode="Markdown",
                    reply_markup=get_manage_accounts_keyboard(accounts)
                )

        # 8. Fluxo Interativo de Transferência entre Contas
        elif data == "transfer_start":
            from app.services.account_service import AccountService
            accounts = AccountService.get_accounts(db, ws.id, active_only=True)
            if len(accounts) < 2:
                await query.edit_message_text(
                    "⚠️ *Você precisa de pelo menos 2 contas ativas cadastradas para realizar transferências.*\nCadastre mais contas primeiro!",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(
                    "🔄 *Transferência Entre Contas*\n\n"
                    "📤 *Passo 1 de 2:* Escolha a **Conta de Origem** (de onde sairá o dinheiro):",
                    parse_mode="Markdown",
                    reply_markup=get_transfer_origin_keyboard(accounts)
                )

        elif data.startswith("transfer_from_"):
            from_id = int(data.replace("transfer_from_", ""))
            from app.services.account_service import AccountService
            from app.models import Account
            from_acc = db.query(Account).filter(Account.id == from_id).first()
            accounts = AccountService.get_accounts(db, ws.id, active_only=True)
            
            if not from_acc:
                await query.edit_message_text("⚠️ Conta de origem não encontrada.", parse_mode="Markdown")
            else:
                await query.edit_message_text(
                    f"🔄 *Transferência Entre Contas*\n\n"
                    f"📤 *Origem selecionada:* {from_acc.icon} *{from_acc.name}* (Saldo: {format_currency_br(from_acc.current_balance)})\n\n"
                    f"📥 *Passo 2 de 2:* Escolha a **Conta de Destino** (para onde vai o dinheiro):",
                    parse_mode="Markdown",
                    reply_markup=get_transfer_dest_keyboard(accounts, from_id)
                )

        elif data.startswith("transfer_to_"):
            parts = data.replace("transfer_to_", "").split("_")
            from_id = int(parts[0])
            to_id = int(parts[1])
            from app.models import Account
            from_acc = db.query(Account).filter(Account.id == from_id).first()
            to_acc = db.query(Account).filter(Account.id == to_id).first()
            
            if not from_acc or not to_acc:
                await query.edit_message_text("⚠️ Contas não encontradas.", parse_mode="Markdown")
            else:
                msg = (
                    f"🔄 *Transferência Selecionada!*\n\n"
                    f"📤 *De (Origem):* {from_acc.icon} {from_acc.name}\n"
                    f"📥 *Para (Destino):* {to_acc.icon} {to_acc.name}\n\n"
                    f"💡 *Para concluir, envie uma mensagem com o valor:*\n"
                    f"Exemplo: `transferir 100 do {from_acc.name} pro {to_acc.name}`"
                )
                await query.edit_message_text(msg, parse_mode="Markdown")



        # 8. Edição e Exclusão de Lançamentos Efetivados
        elif data == "manage_edit_tx":
            from app.models import Transaction
            txs = db.query(Transaction).filter(Transaction.workspace_id == ws.id).order_by(Transaction.transaction_date.desc()).limit(10).all()
            if not txs:
                await query.edit_message_text("📭 Nenhuma movimentação recente para editar.", parse_mode="Markdown")
            else:
                await query.edit_message_text(
                    "✏️ *Selecione o lançamento que deseja editar:*\n_(Você poderá alterar o valor, a data, a categoria ou a descrição)_",
                    parse_mode="Markdown",
                    reply_markup=get_edit_transactions_keyboard(txs)
                )

        elif data.startswith("menu_edit_tx_"):
            tx_id = int(data.split("_")[-1])
            from app.models import Transaction
            tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            if not tx:
                await query.edit_message_text("⚠️ Lançamento não encontrado.", parse_mode="Markdown")
            else:
                tipo_str = "🟢 Receita / Entrada" if tx.type == "income" else "🔴 Despesa / Saída"
                cat_name = tx.category.name if tx.category else "Outros"
                acc_name = tx.account.name if tx.account else tx.payment_method
                msg = (
                    f"✏️ *Editar Lançamento*\n\n"
                    f"📝 *Descrição:* {tx.description}\n"
                    f"💰 *Valor:* {format_currency_br(tx.amount)} ({tipo_str})\n"
                    f"📅 *Data:* {tx.transaction_date.strftime('%d/%m/%Y')}\n"
                    f"🏷️ *Categoria:* {cat_name}\n"
                    f"💳 *Conta:* {acc_name}\n\n"
                    f"👇 *Selecione o que deseja alterar:*"
                )
                await query.edit_message_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=get_transaction_edit_options_keyboard(
                        tx.id,
                        has_items=bool(tx.items_count > 0),
                        items_count=tx.items_count
                    )
                )

        elif data.startswith("prompt_tx_amount_"):
            tx_id = int(data.split("_")[-1])
            from app.models import Transaction
            tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            if tx:
                context.user_data["waiting_tx_amount_id"] = tx.id
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Voltar", callback_data=f"menu_edit_tx_{tx.id}")
                ]])
                await query.edit_message_text(
                    f"💰 *Alterar Valor do Lançamento*\n\n"
                    f"📝 Lançamento: *{tx.description}*\n"
                    f"💵 Valor Atual: *{format_currency_br(tx.amount)}*\n\n"
                    f"Envie uma mensagem de texto com o novo valor (ex: `45,50` ou `120`):\n"
                    f"_(O saldo da conta vinculada será recalculado e ajustado automaticamente)_",
                    parse_mode="Markdown",
                    reply_markup=markup
                )

        elif data.startswith("menu_tx_date_"):
            tx_id = int(data.split("_")[-1])
            from app.models import Transaction
            tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            if tx:
                msg = (
                    f"📅 *Alterar Data do Lançamento*\n\n"
                    f"📝 Lançamento: *{tx.description}*\n"
                    f"🗓️ Data Atual: *{tx.transaction_date.strftime('%d/%m/%Y')}*\n\n"
                    f"👇 *Escolha uma opção de data ou digite uma data específica:*"
                )
                await query.edit_message_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=get_transaction_date_options_keyboard(tx.id)
                )

        elif data.startswith("set_tx_date_"):
            parts = data.split("_")
            tx_id = int(parts[3])
            preset = parts[4]
            import datetime
            now = datetime.datetime.now()
            if preset == "today":
                target_date = now
            elif preset == "yesterday":
                target_date = now - datetime.timedelta(days=1)
            elif preset == "2days":
                target_date = now - datetime.timedelta(days=2)
            else:
                target_date = now

            tx = FinanceService.update_transaction(db, tx_id, transaction_date=target_date)
            if tx:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("📑 Voltar ao Extrato", callback_data="back_to_extrato")
                ]])
                await query.edit_message_text(
                    f"✅ *Data do Lançamento Atualizada!*\n\n"
                    f"📝 *{tx.description}*\n"
                    f"📅 Nova Data: *{target_date.strftime('%d/%m/%Y')}*",
                    parse_mode="Markdown",
                    reply_markup=markup
                )

        elif data.startswith("prompt_tx_date_"):
            tx_id = int(data.split("_")[-1])
            from app.models import Transaction
            tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            if tx:
                context.user_data["waiting_tx_date_id"] = tx.id
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Voltar", callback_data=f"menu_edit_tx_{tx.id}")
                ]])
                await query.edit_message_text(
                    f"📅 *Digitar Nova Data do Lançamento*\n\n"
                    f"📝 Lançamento: *{tx.description}*\n"
                    f"🗓️ Data Atual: *{tx.transaction_date.strftime('%d/%m/%Y')}*\n\n"
                    f"Envie a nova data desejada no formato `DD/MM` ou `DD/MM/AAAA` (ex: `15/09` ou `10/08/2026`):",
                    parse_mode="Markdown",
                    reply_markup=markup
                )

        elif data.startswith("prompt_tx_cat_"):
            tx_id = int(data.split("_")[-1])
            from app.models import Transaction
            tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            if tx:
                context.user_data["waiting_tx_cat_id"] = tx.id
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Voltar", callback_data=f"menu_edit_tx_{tx.id}")
                ]])
                await query.edit_message_text(
                    f"🏷️ *Alterar Categoria do Lançamento*\n\n"
                    f"📝 Lançamento: *{tx.description}*\n"
                    f"🏷️ Categoria Atual: *{tx.category.name if tx.category else 'Outros'}*\n\n"
                    f"Envie o nome da nova categoria (ex: `Alimentação`, `Moradia`, `Transporte`, `Lazer`):",
                    parse_mode="Markdown",
                    reply_markup=markup
                )

        elif data.startswith("prompt_tx_desc_"):
            tx_id = int(data.split("_")[-1])
            from app.models import Transaction
            tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            if tx:
                context.user_data["waiting_tx_desc_id"] = tx.id
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Voltar", callback_data=f"menu_edit_tx_{tx.id}")
                ]])
                await query.edit_message_text(
                    f"📝 *Alterar Descrição do Lançamento*\n\n"
                    f"Descrição Atual: *{tx.description}*\n\n"
                    f"Envie a nova descrição desejada para este lançamento:",
                    parse_mode="Markdown",
                    reply_markup=markup
                )

        # 9. Exclusão de Lançamentos
        elif data == "manage_del_tx":
            from app.models import Transaction
            txs = db.query(Transaction).filter(Transaction.workspace_id == ws.id).order_by(Transaction.transaction_date.desc()).limit(10).all()
            if not txs:
                await query.edit_message_text("📭 Nenhuma movimentação recente para excluir.", parse_mode="Markdown")
            else:
                await query.edit_message_text(
                    "🗑️ *Selecione o lançamento que deseja excluir:*\n_(O saldo da conta vinculada será estornado automaticamente)_",
                    parse_mode="Markdown",
                    reply_markup=get_delete_transactions_keyboard(txs)
                )

        elif data.startswith("del_tx_"):
            tx_id = int(data.split("_")[-1])
            FinanceService.delete_transaction(db, tx_id)
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("📑 Voltar ao Extrato", callback_data="back_to_extrato")
            ]])
            await query.edit_message_text("🗑️ *Lançamento excluído e saldo estornado com sucesso!*", parse_mode="Markdown", reply_markup=markup)

        elif data == "list_cupons":
            from app.models import Transaction
            all_txs = db.query(Transaction).filter(
                Transaction.workspace_id == ws.id
            ).order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).all()
            recent_with_items = [t for t in all_txs if t.items and len(t.items) > 0]

            if not recent_with_items:
                await query.edit_message_text(
                    "📭 *Nenhum cupom fiscal ou compra com itens detalhados foi encontrado neste perfil.*",
                    parse_mode="Markdown"
                )
            else:
                msg = (
                    f"🧾 *Meus Cupons Fiscais & Compras com Itens ({ws.name})*\n"
                    f"───────────────────\n"
                    f"Selecione um cupom abaixo para visualizar a lista completa de produtos comprados, quantidades e preços:"
                )
                await query.edit_message_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=get_cupons_list_keyboard(recent_with_items)
                )

        elif data.startswith("txitems_"):
            tx_id = int(data.split("_")[-1])
            from app.models import Transaction
            tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            if not tx:
                await query.edit_message_text("⚠️ Lançamento não encontrado.", parse_mode="Markdown")
            else:
                items = FinanceService.get_transaction_items(db, tx_id)
                all_txs = db.query(Transaction).filter(
                    Transaction.workspace_id == ws.id
                ).order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).all()
                recent_with_items = [t for t in all_txs if t.items and len(t.items) > 0]

                prev_id = None
                next_id = None
                if tx in recent_with_items:
                    idx = recent_with_items.index(tx)
                    prev_id = recent_with_items[idx + 1].id if idx + 1 < len(recent_with_items) else None
                    next_id = recent_with_items[idx - 1].id if idx > 0 else None

                receipt_text = format_full_receipt_text(tx, items)
                await query.edit_message_text(
                    receipt_text,
                    parse_mode="Markdown",
                    reply_markup=get_cupom_detail_keyboard(tx.id, prev_id=prev_id, next_id=next_id)
                )

        elif data.startswith("txaccmenu_"):
            tx_id = int(data.split("_")[-1])
            from app.models import Transaction
            from app.services.account_service import AccountService
            tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            if tx:
                accounts = AccountService.get_accounts(db, ws.id)
                markup = get_accounts_selection_keyboard(
                    tx.id,
                    accounts,
                    tx.account_id,
                    has_items=bool(tx.items_count > 0),
                    items_count=tx.items_count
                )
                summary = FinanceService.get_monthly_summary(db, ws.id)
                saldo_emoji = "🟢" if summary["net_balance"] >= 0 else "🔴"
                tipo_icon = "🟢 Entrada" if tx.type == "income" else "🔴 Saída"
                cat_name = tx.category.name if tx.category else "Outros"
                msg = (
                    f"🧾 *Lançamento Selecionado:*\n\n"
                    f"{tipo_icon}: *{format_currency_br(tx.amount)}* ({tx.description})\n"
                    f"🏷️ Categoria: _{cat_name}_ • 💳 Conta: *{tx.payment_method}*\n"
                    f"🛒 Itens: *{tx.items_count} produtos discriminados*\n\n"
                    f"📍 *Perfil:* `{ws.name}`\n"
                    f"{saldo_emoji} *Novo Saldo do Mês:* {format_currency_br(summary['net_balance'])}\n\n"
                    f"👇 *Selecione ou troque a conta bancária/cartão abaixo:*"
                )
                await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=markup)

        elif data.startswith("txdelitems_"):
            tx_id = int(data.split("_")[-1])
            from app.models import Transaction
            tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            if tx:
                FinanceService.delete_transaction_items(db, tx_id)
                await query.edit_message_text(
                    f"✅ *Detalhamento de Itens Removido!*\n\n"
                    f"O lançamento *{tx.description}* foi mantido no valor total consolidado de *{format_currency_br(tx.amount)}*.",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("⚠️ Lançamento não encontrado.", parse_mode="Markdown")

        elif data.startswith("filter_tx_"):
            parts = data.split("_")
            acc_id_int = int(parts[2])
            filter_type = parts[3]

            acc_id_param = None if acc_id_int == 0 else acc_id_int
            tx_type_param = None if filter_type == "all" else filter_type

            from app.models import Account, Transaction
            target_acc = db.query(Account).filter(Account.id == acc_id_param).first() if acc_id_param else None

            txs = FinanceService.get_filtered_transactions(
                db=db,
                workspace_id=ws.id,
                tx_type=tx_type_param,
                account_id=acc_id_param,
                limit=8
            )

            acc_name = f" - {target_acc.icon} {target_acc.name}" if target_acc else ""
            type_badge = " (🔴 Só Despesas)" if filter_type == "expense" else (" (🟢 Só Receitas)" if filter_type == "income" else "")
            title = f"📑 *Extrato: {ws.name}{acc_name}{type_badge}*"

            if not txs:
                msg = f"{title}\n───────────────────\n📭 Nenhuma movimentação encontrada para este filtro."
            else:
                msg = f"{title}\n───────────────────\n"
                for t in txs:
                    icon = "🟢 +" if t.type == "income" else "🔴 -"
                    cat = t.category.name if t.category else "Outros"
                    dt = t.transaction_date.strftime("%d/%m")
                    items_badge = f" • 🛒 {t.items_count} itens" if t.items_count > 0 else ""
                    acc_label = t.account.name if t.account else t.payment_method
                    msg += f"{icon} *{format_currency_br(t.amount)}* | {t.description}{items_badge}\n   🏷️ _{cat}_ • 💳 _{acc_label}_ • 📅 _{dt}_\n\n"

            await query.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_extrato_keyboard(txs=txs, current_type=filter_type, current_acc_id=acc_id_param)
            )

        elif data.startswith("filter_acc_menu_"):
            current_type = data.replace("filter_acc_menu_", "")
            from app.services.account_service import AccountService
            accounts = AccountService.get_accounts(db, ws.id)
            msg = (
                f"🏦 *Filtrar Lançamentos por Conta Bancária*\n"
                f"📍 *Contexto:* `{ws.name}`\n"
                f"───────────────────\n"
                f"Selecione uma conta para ver somente as movimentações vinculadas a ela:"
            )
            await query.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_account_filter_keyboard(accounts, current_type=current_type)
            )

        elif data == "expenses_by_account":
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

            await query.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_expenses_by_account_keyboard(summary["accounts"])
            )

        elif data == "back_to_extrato":
            from app.models import Transaction
            txs = FinanceService.get_filtered_transactions(db, ws.id, limit=8)
            if not txs:
                await query.edit_message_text("📭 Nenhuma movimentação recente registrada neste perfil.", parse_mode="Markdown")
            else:
                msg = f"📑 *Últimos Lançamentos - {ws.name}:*\n───────────────────\n"
                for t in txs:
                    icon = "🟢 +" if t.type == "income" else "🔴 -"
                    cat = t.category.name if t.category else "Outros"
                    dt = t.transaction_date.strftime("%d/%m")
                    items_badge = f" • 🛒 {t.items_count} itens" if t.items_count > 0 else ""
                    acc_label = t.account.name if t.account else t.payment_method
                    msg += f"{icon} *{format_currency_br(t.amount)}* | {t.description}{items_badge}\n   🏷️ _{cat}_ • 💳 _{acc_label}_ • 📅 _{dt}_\n\n"
                await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_extrato_keyboard(txs, current_type="all", current_acc_id=None))

        elif data.startswith("dup_confirm_"):
            token = data.replace("dup_confirm_", "")
            from app.bot.handlers.pending_duplicate import pop_pending_duplicate
            from app.services.account_service import AccountService
            import datetime

            pending = pop_pending_duplicate(token)
            if not pending:
                await query.edit_message_text(
                    "⚠️ *Esta solicitação de confirmação expirou ou já foi processada.*\n\n"
                    "Por favor, envie o comprovante ou gasto novamente se desejar cadastrar.",
                    parse_mode="Markdown"
                )
            else:
                try:
                    tx_date = datetime.datetime.fromisoformat(pending["transaction_date"])
                except Exception:
                    tx_date = datetime.datetime.utcnow()

                tx = FinanceService.add_transaction(
                    db=db,
                    workspace_id=pending["workspace_id"],
                    user_id=pending["user_id"],
                    type=pending["type"],
                    amount=pending["amount"],
                    description=pending["description"],
                    category_name=pending["category_name"],
                    payment_method=pending["payment_method"],
                    transaction_date=tx_date,
                    receipt_url=pending["receipt_url"],
                    items=pending["items"]
                )

                summary = FinanceService.get_monthly_summary(db, ws.id)
                saldo_emoji = "🟢" if summary["net_balance"] >= 0 else "🔴"
                tipo_icon = "🟢 Entrada" if tx.type == "income" else "🔴 Saída"
                cat_name = tx.category.name if tx.category else "Outros"
                acc_name = tx.payment_method

                item_line = f"{tipo_icon}: *{format_currency_br(tx.amount)}* ({tx.description})\n🏷️ Categoria: _{cat_name}_ • 💳 Conta: *{acc_name}*"
                if tx.items_count > 0:
                    item_line += format_items_list_text(tx.items, max_items=25)

                msg = (
                    f"✅ *Lançamento Cadastrado com Sucesso (Duplicidade Confirmada)!*\n\n"
                    f"{item_line}\n\n"
                    f"📍 *Perfil:* `{ws.name}`\n"
                    f"{saldo_emoji} *Novo Saldo do Mês:* {format_currency_br(summary['net_balance'])}\n\n"
                    f"👇 *Selecione ou troque a conta bancária/cartão abaixo:*"
                )
                accounts = AccountService.get_accounts(db, ws.id)
                markup = get_accounts_selection_keyboard(
                    tx.id,
                    accounts,
                    tx.account_id,
                    has_items=bool(tx.items_count > 0),
                    items_count=tx.items_count
                )
                try:
                    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=markup)
                except Exception:
                    await query.edit_message_text(msg, reply_markup=markup)

        elif data.startswith("dup_cancel_"):
            token = data.replace("dup_cancel_", "")
            from app.bot.handlers.pending_duplicate import delete_pending_duplicate
            delete_pending_duplicate(token)
            await query.edit_message_text(
                "❌ *Lançamento cancelado.*\n\n"
                "Nenhum registro foi criado no seu extrato e seus saldos permanecem inalterados.",
                parse_mode="Markdown"
            )


    finally:
        db.close()
