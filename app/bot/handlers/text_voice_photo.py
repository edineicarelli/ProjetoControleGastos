import os
import datetime
from telegram import Update
from telegram.ext import ContextTypes
from app.database import SessionLocal
from app.config import settings
from app.services.finance_service import FinanceService
from app.services.ai_service import ai_service
from app.services.reminder_service import ReminderService
from app.services.goal_service import GoalService
from app.services.vehicle_service import VehicleService
from app.services.shopping_service import ShoppingService
from app.bot.keyboards import get_dashboard_link_keyboard, get_profile_inline_keyboard
from app.utils import format_currency_br, format_number_br

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens de texto livre com IA"""
    text = update.message.text.strip()
    user_tg = update.effective_user

    # Se for um dos botões do Reply Keyboard, redireciona para a função correta
    if text == "📊 Saldo do Mês":
        from app.bot.handlers.commands import saldo_handler
        return await saldo_handler(update, context)
    elif text == "📑 Últimos Gastos":
        from app.bot.handlers.commands import extrato_handler
        return await extrato_handler(update, context)
    elif text == "💳 Minhas Contas / Bancos":
        from app.bot.handlers.commands import contas_handler
        return await contas_handler(update, context)
    elif text == "👤/🏢 Alternar Perfil":
        from app.bot.handlers.commands import perfil_handler
        return await perfil_handler(update, context)
    elif text == "⏰ Contas a Vencer":
        from app.bot.handlers.commands import lembretes_handler
        return await lembretes_handler(update, context)
    elif text == "🎯 Minhas Metas":
        from app.bot.handlers.commands import metas_handler
        return await metas_handler(update, context)
    elif text == "🛒 Lista de Mercado":
        from app.bot.handlers.commands import mercado_handler
        return await mercado_handler(update, context)
    elif text == "🚗 Manutenção Veículo":
        from app.bot.handlers.commands import veiculo_handler
        return await veiculo_handler(update, context)
    elif text == "🌐 Abrir Painel Web":
        from app.bot.handlers.commands import painel_handler
        return await painel_handler(update, context)

    # Feedback imediato de digitação
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    db = SessionLocal()
    try:
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id), user_tg.full_name, user_tg.username)
        
        user_context = {
            "user_name": user.name,
            "workspace_name": ws.name,
            "workspace_type": ws.type
        }

        text_lower = text.lower()
        if any(w in text_lower for w in ["criar conta", "nova conta", "cadastrar conta", "adicionar conta"]):
            import re
            from app.services.account_service import AccountService
            from app.bot.keyboards import get_account_detail_keyboard
            
            val_match = re.search(r"(?:saldo\s*(?:inicial)?\s*(?:de)?\s*|r\$\s*)(\d+(?:[.,]\d{1,2})?)", text_lower)
            init_bal = float(val_match.group(1).replace(",", ".")) if val_match else 0.0
            
            clean = re.sub(r"(?:criar\s+conta|nova\s+conta|cadastrar\s+conta|adicionar\s+conta)\s*", "", text, flags=re.IGNORECASE)
            clean = re.sub(r"(?:saldo\s*(?:inicial)?\s*(?:de)?\s*|r\$\s*)\d+(?:[.,]\d{1,2})?", "", clean, flags=re.IGNORECASE).strip()
            if not clean:
                clean = "Nova Conta"
                
            acc_name = clean.title()
            icon = "🏦"
            acc_type = "checking"
            color = "#6366f1"
            if any(b in clean.lower() for b in ["dinheiro", "carteira", "especie"]):
                icon = "💵"
                acc_type = "cash"
                color = "#10b981"
            elif "cartao" in clean.lower() or "cartão" in clean.lower():
                icon = "💳"
                acc_type = "credit_card"
                color = "#f43f5e"
            elif "poupanca" in clean.lower() or "poupança" in clean.lower():
                icon = "🪙"
                acc_type = "savings"
                color = "#f59e0b"
            elif "nubank" in clean.lower() or "nu" in clean.lower():
                icon = "🟣"
                color = "#8b5cf6"
            elif "inter" in clean.lower():
                icon = "🟠"
                color = "#f97316"
            elif "santander" in clean.lower():
                icon = "🔴"
                color = "#ef4444"
            elif "caixa" in clean.lower():
                icon = "🔵"
                color = "#3b82f6"
            elif "bb" in clean.lower() or "banco do brasil" in clean.lower():
                icon = "🟡"
                color = "#fbbf24"
            elif "itau" in clean.lower() or "itaú" in clean.lower():
                icon = "🟠"
                color = "#ea580c"

            acc = AccountService.create_account(
                db=db,
                workspace_id=ws.id,
                name=acc_name,
                type=acc_type,
                initial_balance=init_bal,
                icon=icon,
                color=color
            )
            msg = (
                f"✅ *Conta Bancária / Carteira Criada!*\n\n"
                f"🏦 *Nome:* {acc.icon} {acc.name}\n"
                f"📑 *Tipo:* `{acc.type.upper()}`\n"
                f"💰 *Saldo Inicial:* {format_currency_br(acc.initial_balance)}\n"
                f"📌 *Status:* 🟢 Ativa\n\n"
                f"💡 _Agora você pode vincular lançamentos a esta conta!_"
            )
            await update.message.reply_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_account_detail_keyboard(acc)
            )
            return

        elif any(w in text_lower for w in ["inativar conta", "desativar conta", "pausar conta", "reativar conta", "ativar conta"]):
            import re
            from app.services.account_service import AccountService
            from app.bot.keyboards import get_account_detail_keyboard
            target_name = re.sub(r"(?:inativar\s+conta|desativar\s+conta|pausar\s+conta|reativar\s+conta|ativar\s+conta)\s*", "", text, flags=re.IGNORECASE).strip()
            acc = AccountService.find_account_by_name(db, ws.id, target_name)
            if acc:
                acc = AccountService.toggle_account_active(db, acc.id)
                status_str = "🟢 Ativa" if (acc.is_active != False) else "⏸️ Inativa"
                msg = (
                    f"💳 *Status da Conta Atualizado!*\n\n"
                    f"🏦 *Conta:* {acc.icon} {acc.name}\n"
                    f"📌 *Novo Status:* {status_str}\n"
                    f"💰 *Saldo Atual:* {format_currency_br(acc.current_balance)}"
                )
                await update.message.reply_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=get_account_detail_keyboard(acc)
                )
                return
            else:
                await update.message.reply_text(f"⚠️ Conta *{target_name}* não encontrada neste perfil.", parse_mode="Markdown")
                return

        # Chama a IA para processar
        parsed = await ai_service.parse_text(text, user_context)

        # Executa a ação detectada pela IA
        response_msg, markup = await _apply_parsed_result(db, user, ws, parsed)

        await update.message.reply_text(
            response_msg,
            parse_mode="Markdown",
            reply_markup=markup or get_dashboard_link_keyboard(str(user_tg.id))
        )
    finally:
        db.close()

async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa áudios e notas de voz do Telegram"""
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")

    file_obj = await context.bot.get_file(voice.file_id)
    file_ext = ".ogg" if update.message.voice else ".mp3"
    file_path = os.path.join(settings.UPLOAD_DIR, "audio", f"voice_{voice.file_id}{file_ext}")
    await file_obj.download_to_drive(file_path)

    db = SessionLocal()
    try:
        user_tg = update.effective_user
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id), user_tg.full_name, user_tg.username)

        user_context = {
            "user_name": user.name,
            "workspace_name": ws.name,
            "workspace_type": ws.type
        }

        parsed = await ai_service.parse_audio(file_path, user_context)
        response_msg, markup = await _apply_parsed_result(db, user, ws, parsed)

        await update.message.reply_text(
            f"🎙️ *Áudio Processado!*\n\n{response_msg}",
            parse_mode="Markdown",
            reply_markup=markup or get_dashboard_link_keyboard(str(user_tg.id))
        )
    finally:
        db.close()

async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa fotos de comprovantes e notas fiscais"""
    photos = update.message.photo
    if not photos:
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")

    photo = photos[-1]  # Maior resolução
    file_obj = await context.bot.get_file(photo.file_id)
    file_path = os.path.join(settings.UPLOAD_DIR, "receipts", f"receipt_{photo.file_id}.jpg")
    await file_obj.download_to_drive(file_path)

    db = SessionLocal()
    try:
        user_tg = update.effective_user
        user, ws = FinanceService.get_or_create_user(db, str(user_tg.id), user_tg.full_name, user_tg.username)

        user_context = {
            "user_name": user.name,
            "workspace_name": ws.name,
            "workspace_type": ws.type
        }

        parsed = await ai_service.parse_receipt_image(file_path, user_context)
        response_msg, markup = await _apply_parsed_result(db, user, ws, parsed, receipt_url=file_path)

        await update.message.reply_text(
            f"📸 *Comprovante Lido com Sucesso!*\n\n{response_msg}",
            parse_mode="Markdown",
            reply_markup=markup or get_dashboard_link_keyboard(str(user_tg.id))
        )
    finally:
        db.close()

async def _apply_parsed_result(db, user, ws, parsed, receipt_url=None):
    """Executa a lógica no banco de acordo com o retorno estruturado da IA e retorna mensagem e botões"""
    intent = parsed.intent
    from app.services.account_service import AccountService
    from app.bot.keyboards import get_accounts_selection_keyboard

    # 1. Transações financeiras
    if intent == "transaction_record" and parsed.transactions:
        saved_items = []
        last_tx = None
        for t in parsed.transactions:
            date = datetime.datetime.utcnow() + datetime.timedelta(days=t.date_offset_days)
            tx = FinanceService.add_transaction(
                db=db,
                workspace_id=ws.id,
                user_id=user.id,
                type=t.type,
                amount=t.amount,
                description=t.description,
                category_name=t.category_name,
                payment_method=t.payment_method,
                transaction_date=date,
                receipt_url=receipt_url
            )
            last_tx = tx
            tipo_icon = "🟢 Entrada" if tx.type == "income" else "🔴 Saída"
            cat_name = tx.category.name if tx.category else "Outros"
            acc_name = tx.payment_method
            saved_items.append(f"{tipo_icon}: *{format_currency_br(tx.amount)}* ({t.description})\n🏷️ Categoria: _{cat_name}_ • 💳 Conta: *{acc_name}*")

        summary = FinanceService.get_monthly_summary(db, ws.id)
        saldo_emoji = "🟢" if summary["net_balance"] >= 0 else "🔴"
        
        msg = (
            f"✅ *Lançamento Registrado!*\n\n"
            + "\n\n".join(saved_items) + "\n\n"
            f"📍 *Perfil:* `{ws.name}`\n"
            f"{saldo_emoji} *Novo Saldo do Mês:* {format_currency_br(summary['net_balance'])}\n\n"
            f"👇 *Selecione ou troque a conta bancária/cartão abaixo:*"
        )
        accounts = AccountService.get_accounts(db, ws.id)
        markup = get_accounts_selection_keyboard(last_tx.id, accounts, last_tx.account_id) if last_tx else None
        return msg, markup

    # 2. Transferência entre contas / Bancos / Carteiras
    elif intent == "account_transfer" and parsed.transfer:
        tr = parsed.transfer
        from_acc = AccountService.find_account_by_name(db, ws.id, tr.from_account)
        to_acc = AccountService.find_account_by_name(db, ws.id, tr.to_account)

        # Fallback inteligente se nomes forem ligeiramente diferentes
        accounts = AccountService.get_accounts(db, ws.id, active_only=True)
        if not from_acc and accounts:
            for a in accounts:
                if any(w in a.name.lower() for w in tr.from_account.lower().split()):
                    from_acc = a
                    break
        if not to_acc and accounts:
            for a in accounts:
                if any(w in a.name.lower() for w in tr.to_account.lower().split()):
                    to_acc = a
                    break

        if not from_acc or not to_acc or from_acc.id == to_acc.id:
            acc_list = "\n".join([f"• {a.icon} {a.name} ({format_currency_br(a.current_balance)})" for a in accounts])
            return (
                f"⚠️ *Não consegui identificar com precisão as duas contas para a transferência.*\n\n"
                f"📋 *Contas ativas neste perfil:*\n{acc_list}\n\n"
                f"💡 *Exemplo de comando:* `Transferir 100 do Nubank pro Santander` ou `Saquei 50 da Caixa`",
                None
            )

        res = AccountService.transfer_between_accounts(
            db=db,
            workspace_id=ws.id,
            user_id=user.id,
            from_account_id=from_acc.id,
            to_account_id=to_acc.id,
            amount=tr.amount,
            description=tr.description
        )

        transfer_msg = (
            f"🔄 *Transferência Realizada com Sucesso!*\n\n"
            f"💰 *Valor:* {format_currency_br(tr.amount)}\n"
            f"📤 *Origem (Debitado):* {from_acc.icon} {from_acc.name} → Saldo: *{format_currency_br(from_acc.current_balance)}*\n"
            f"📥 *Destino (Creditado):* {to_acc.icon} {to_acc.name} → Saldo: *{format_currency_br(to_acc.current_balance)}*\n"
            f"📍 *Perfil:* `{ws.name}`\n\n"
            f"✨ _Lançamentos criados no extrato e saldos atualizados no painel web!_"
        )
        return transfer_msg, None

    # 3. Lembretes / Contas
    elif intent == "reminder_create" and parsed.reminder:
        r = parsed.reminder
        try:
            due_dt = datetime.datetime.strptime(r.due_date, "%Y-%m-%d")
        except:
            due_dt = datetime.datetime.utcnow() + datetime.timedelta(days=5)

        rem = ReminderService.create_reminder(
            db=db,
            workspace_id=ws.id,
            user_id=user.id,
            title=r.title,
            amount=r.amount,
            due_date=due_dt,
            type=r.type,
            recurrence=r.recurrence
        )
        rem_msg = (
            f"⏰ *Conta / Lembrete Agendado!*\n\n"
            f"📝 *{rem.title}*\n"
            f"💰 Valor: *{format_currency_br(rem.amount)}*\n"
            f"📅 Vencimento: *{rem.due_date.strftime('%d/%m/%Y')}*\n\n"
            f"🔔 Você receberá um alerta automático antes do vencimento!"
        )
        return rem_msg, None

    # 3. Metas / Caixinhas
    elif intent == "goal_action" and parsed.goal:
        g = parsed.goal
        goal = GoalService.deposit_by_name(db, ws.id, g.goal_name, g.amount)
        bar = GoalService.get_progress_bar(goal.progress_percentage)
        goal_msg = (
            f"🎯 *Meta Atualizada: {goal.title}*\n\n"
            f"💰 Guardado: *{format_currency_br(goal.current_amount)}* de *{format_currency_br(goal.target_amount)}*\n"
            f"📊 Progresso: `{bar}`"
        )
        return goal_msg, None

    # 4. Veículo
    elif intent == "vehicle_action" and parsed.vehicle:
        v = parsed.vehicle
        vehicle = VehicleService.get_or_create_vehicle(db, ws.id)
        maint = VehicleService.add_maintenance(
            db=db,
            vehicle_id=vehicle.id,
            type=v.type,
            description=v.description,
            amount=v.amount,
            km=v.km,
            next_due_km=v.next_due_km
        )
        # Registra também como despesa se houver valor
        if v.amount > 0:
            FinanceService.add_transaction(
                db=db,
                workspace_id=ws.id,
                user_id=user.id,
                type="expense",
                amount=v.amount,
                description=f"{vehicle.name}: {v.description}",
                category_name="Transporte",
                payment_method="Cartão"
            )
        veh_msg = (
            f"🚗 *Registro Veicular Salvo!*\n\n"
            f"🚘 Veículo: *{vehicle.name}* (KM: {format_number_br(vehicle.current_km)})\n"
            f"🛠️ Ação: *{maint.description}*\n"
            f"💰 Valor: *{format_currency_br(maint.amount)}*"
        )
        return veh_msg, None

    # 5. Lista de compras
    elif intent == "shopping_action" and parsed.shopping and parsed.shopping.items:
        s_list = ShoppingService.get_or_create_active_list(db, ws.id)
        added = []
        for it in parsed.shopping.items:
            item = ShoppingService.add_item(
                db=db,
                list_id=s_list.id,
                name=it.name,
                quantity=it.quantity,
                unit=it.unit,
                estimated_price=it.estimated_price
            )
            added.append(f"• {item.name} ({item.quantity:.0f} {item.unit})")
        return f"🛒 *Itens adicionados à Lista de Mercado:*\n\n" + "\n".join(added), None

    # 6. Troca de perfil
    elif intent == "profile_switch" and parsed.target_profile:
        new_ws = FinanceService.switch_workspace(db, user, parsed.target_profile)
        return f"🔄 *Perfil alternado para:* `{new_ws.name}`\nTodos os próximos lançamentos serão registrados nesta conta.", None

    # Resposta amigável padrão
    return parsed.friendly_response, None
