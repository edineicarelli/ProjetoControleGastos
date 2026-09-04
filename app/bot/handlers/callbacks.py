import os
from telegram import Update
from telegram.ext import ContextTypes
from app.database import SessionLocal
from app.services.finance_service import FinanceService
from app.services.reminder_service import ReminderService
from app.services.shopping_service import ShoppingService
from app.services.export_service import ExportService
from app.bot.keyboards import get_profile_inline_keyboard, get_account_detail_keyboard, get_quick_add_accounts_keyboard, get_manage_accounts_keyboard
from app.utils import format_currency_br

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerencia cliques em botões inline do Telegram"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_tg = update.effective_user
    db = SessionLocal()

    try:
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id), user_tg.full_name, user_tg.username)

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

        # 2. Ações em Lembretes / Contas
        elif data.startswith("pay_reminder_"):
            r_id = int(data.split("_")[-1])
            rem = ReminderService.mark_as_paid(db, r_id)
            if rem:
                # Registra a transação de despesa automaticamente
                FinanceService.add_transaction(
                    db=db,
                    workspace_id=rem.workspace_id,
                    user_id=user.id,
                    type="expense" if rem.type == "to_pay" else "income",
                    amount=rem.amount,
                    description=f"Pagamento de conta: {rem.title}",
                    category_name="Contas & Serviços",
                    payment_method="Boleto/Pix"
                )
                await query.edit_message_text(f"✅ Conta *{rem.title}* ({format_currency_br(rem.amount)}) marcada como PAGA e lançada no extrato!", parse_mode="Markdown")

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
            web_url = f"{settings.BASE_URL}/dashboard?user_id={tg_id}"
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton(text="🚀 Abrir Painel Financeiro", url=web_url)
            ]])
            await query.message.reply_text(
                f"🌐 <b>Acesse seu Painel Financeiro Web no link:</b>\n"
                f"<code>{web_url}</code>\n\n"
                f"<i>(Abra no seu navegador para ver gráficos completos, relatórios e exportações)</i>",
                parse_mode="HTML",
                reply_markup=markup
            )

        # 6. Vínculo de Conta Bancária na Transação
        elif data.startswith("txacc_"):
            parts = data.split("_")
            tx_id = int(parts[1])
            acc_id = int(parts[2])
            from app.services.account_service import AccountService
            from app.bot.keyboards import get_accounts_selection_keyboard
            
            tx = AccountService.set_transaction_account(db, tx_id, acc_id)
            if tx and tx.account:
                accounts = AccountService.get_accounts(db, ws.id)
                new_markup = get_accounts_selection_keyboard(tx.id, accounts, tx.account_id)
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
                tx_count = len(acc.transactions)
                msg = (
                    f"💳 *Controle da Conta: {acc.icon} {acc.name}*\n"
                    f"───────────────────\n"
                    f"💰 *Saldo Atual:* {format_currency_br(acc.current_balance)}\n"
                    f"🏷️ *Saldo Inicial:* {format_currency_br(acc.initial_balance)}\n"
                    f"📑 *Tipo:* `{acc.type.upper()}`\n"
                    f"📌 *Status:* {status_str}\n"
                    f"📊 *Lançamentos Vinculados:* {tx_count}\n\n"
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
            from app.bot.keyboards import get_transfer_origin_keyboard
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
            from app.bot.keyboards import get_transfer_dest_keyboard
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



        # 8. Exclusão de Lançamentos
        elif data == "manage_del_tx":
            from app.models import Transaction
            from app.bot.keyboards import get_delete_transactions_keyboard
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
            from app.models import Transaction
            tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            if tx:
                desc = tx.description
                val = format_currency_br(tx.amount)
                FinanceService.delete_transaction(db, tx_id)
                summary = FinanceService.get_monthly_summary(db, ws.id)
                await query.edit_message_text(
                    f"🗑️ *Lançamento excluído com sucesso!*\n\n"
                    f"📝 *{desc}* ({val})\n"
                    f"💰 *Novo Saldo do Mês:* {format_currency_br(summary['net_balance'])}",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("⚠️ Lançamento já foi excluído ou não encontrado.", parse_mode="Markdown")

        elif data == "back_to_extrato":
            from app.models import Transaction
            from app.bot.keyboards import get_extrato_keyboard
            txs = db.query(Transaction).filter(Transaction.workspace_id == ws.id).order_by(Transaction.transaction_date.desc()).limit(8).all()
            if not txs:
                await query.edit_message_text("📭 Nenhuma movimentação recente registrada neste perfil.", parse_mode="Markdown")
            else:
                msg = f"📑 *Últimos Lançamentos - {ws.name}:*\n───────────────────\n"
                for t in txs:
                    icon = "🟢 +" if t.type == "income" else "🔴 -"
                    cat = t.category.name if t.category else "Outros"
                    dt = t.transaction_date.strftime("%d/%m")
                    msg += f"{icon} *{format_currency_br(t.amount)}* | {t.description}\n   🏷️ _{cat}_ • 💳 _{t.payment_method}_ • 📅 _{dt}_\n\n"
                await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_extrato_keyboard())


    finally:
        db.close()
