import os
import datetime
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from app.database import SessionLocal
from app.config import settings
from app.services.finance_service import FinanceService
from app.services.auth_service import AuthService
from app.services.ai_service import ai_service
from app.services.reminder_service import ReminderService
from app.services.goal_service import GoalService
from app.services.vehicle_service import VehicleService
from app.services.shopping_service import ShoppingService
from app.bot.keyboards import get_dashboard_link_keyboard, get_profile_inline_keyboard, get_main_reply_keyboard
from app.bot.handlers.auth_helper import get_authenticated_bot_user
from app.utils import format_currency_br, format_number_br

logger = logging.getLogger(__name__)

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens de texto livre com IA após verificar autenticação por senha"""
    text = update.message.text.strip()
    user_tg = update.effective_user

    db = SessionLocal()
    try:
        # 1. Checa autenticação do usuário no Telegram
        is_auth, user, status_code = AuthService.verify_telegram_auth(db, str(user_tg.id))

        if not is_auth:
            # Se a conta está inativa
            if status_code == "inactive":
                await update.message.reply_text(
                    "⛔ *Acesso Bloqueado*\n\nSua conta está inativa no sistema. Entre em contato com o administrador.",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
                return

            # Se o usuário já existe mas ainda não autenticou com senha
            if status_code == "unauthenticated" and user:
                success, msg, auth_user = AuthService.authenticate_telegram_user(
                    db=db,
                    telegram_id=str(user_tg.id),
                    password=text,
                    name=user_tg.full_name or user_tg.first_name
                )

                if success and auth_user:
                    try:
                        await update.message.delete()
                    except Exception:
                        pass

                    await update.message.reply_text(
                        f"✅ *Autenticação realizada com sucesso!*\n\n"
                        f"Bem-vindo(a), *{auth_user.name or auth_user.username}*! Seu acesso ao assistente financeiro no Telegram está liberado.\n\n"
                        f"💡 _Como posso te ajudar hoje? Envie uma mensagem de gasto ou use o menu abaixo._",
                        parse_mode="Markdown",
                        reply_markup=get_main_reply_keyboard()
                    )
                    return
                else:
                    await update.message.reply_text(
                        "❌ *Senha incorreta.*\n\n"
                        "Por favor, digite a mesma senha utilizada para acessar o sistema Web (ou envie `/login usuario senha`).\n\n"
                        "💡 _Esqueceu a senha? Acesse a tela de login na Web e use 'Esqueci minha senha'._",
                        parse_mode="Markdown",
                        reply_markup=ReplyKeyboardRemove()
                    )
                    return

            # Se ainda não possui vínculo de conta (unregistered)
            # Verifica se o texto enviado contém credenciais (ex: "usuario senha")
            parts = text.split(maxsplit=1)
            if len(parts) == 2 and not text.startswith("/"):
                success, msg, auth_user = AuthService.authenticate_telegram_user(
                    db=db,
                    telegram_id=str(user_tg.id),
                    username=parts[0],
                    password=parts[1],
                    name=user_tg.full_name or user_tg.first_name
                )
                if success and auth_user:
                    try:
                        await update.message.delete()
                    except Exception:
                        pass

                    await update.message.reply_text(
                        f"🎉 *Conta vinculada e autenticada com sucesso!*\n\n"
                        f"Olá, *{auth_user.name or auth_user.username}*! Agora você pode registrar despesas e consultar saldos diretamente por aqui.",
                        parse_mode="Markdown",
                        reply_markup=get_main_reply_keyboard()
                    )
                    return

            await update.message.reply_text(
                "🔒 *Acesso Restrito ao Sistema*\n\n"
                "Para utilizar este assistente, vincule sua conta informando seu **Usuário** e **Senha** cadastrados na Web:\n\n"
                "👉 `/login seu_usuario sua_senha`\n\n"
                "_(Exemplo: `/login admin MinhaSenha123`)_",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        # 2. Usuário autenticado: processa botões de menu
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

        if not user.current_workspace:
            _, ws = FinanceService.get_or_create_user(db, str(user_tg.id), user_tg.full_name, user_tg.username)
        else:
            ws = user.current_workspace
        
        user_context = {
            "user_name": user.name,
            "workspace_name": ws.name,
            "workspace_type": ws.type
        }

        text_lower = text.lower()
        if any(w in text_lower for w in ["zerar conta", "zerar contas", "zerar mes", "zerar mês", "limpar conta", "limpar mes", "limpar mês", "zerar gastos", "zerar saldo"]):
            import re
            from app.services.account_service import AccountService
            from app.bot.keyboards import get_zero_selection_keyboard, get_zero_account_confirmation_keyboard
            
            clean_name = re.sub(r"(?:zerar\s+conta|zerar\s+contas|zerar\s+mes|zerar\s+mês|limpar\s+conta|limpar\s+mes|limpar\s+mês|zerar\s+gastos|zerar\s+saldo)\s*(?:do|da|de|no|na)?\s*", "", text, flags=re.IGNORECASE).strip()
            
            if clean_name:
                acc = AccountService.find_account_by_name(db, ws.id, clean_name)
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

            accounts = AccountService.get_accounts(db, ws.id, active_only=True)
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
            return

        if any(w in text_lower for w in ["ver itens", "itens do cupom", "itens do mercado", "itens da compra", "produtos do cupom", "cupom fiscal", "mostrar itens", "quais itens", "detalhes do cupom", "ver cupom"]):
            from app.models import Transaction
            tx_with_items = db.query(Transaction).filter(
                Transaction.workspace_id == ws.id
            ).order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).all()
            
            target_tx = None
            for t in tx_with_items:
                if t.items and len(t.items) > 0:
                    target_tx = t
                    break
            
            if not target_tx:
                await update.message.reply_text(
                    "🛒 *Nenhum cupom fiscal ou compra com itens detalhados foi encontrado neste perfil.*\n\n"
                    "💡 Ao enviar a foto de um cupom de mercado ou cadastrar uma compra com itens, você poderá consultá-los aqui a qualquer momento!",
                    parse_mode="Markdown"
                )
                return

            items = target_tx.items
            lines = [
                f"🧾 *Itens Comprados - {target_tx.description}*",
                f"💰 *Valor Total Pago:* {format_currency_br(target_tx.amount)}",
                f"📅 *Data:* {target_tx.transaction_date.strftime('%d/%m/%Y')} • 🏷️ *Categoria:* {target_tx.category.name if target_tx.category else 'Mercado'}",
                "───────────────────"
            ]
            for idx, it in enumerate(items, 1):
                tot = it.total_price if it.total_price > 0 else (it.quantity * it.unit_price)
                unit_str = f" ({it.quantity:g} {it.unit} x {format_currency_br(it.unit_price)})" if it.unit_price > 0 else f" ({it.quantity:g} {it.unit})"
                lines.append(f"*{idx}.* {it.name}{unit_str} → *{format_currency_br(tot)}*")

            lines.append("───────────────────")
            lines.append(f"📊 *Total de Produtos:* {len(items)} itens discriminados")
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            item_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Manter Só Total (Remover Itens)", callback_data=f"txdelitems_{target_tx.id}")],
                [InlineKeyboardButton("🔙 Voltar ao Extrato", callback_data="back_to_extrato")]
            ])
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=item_markup)
            return

        # Comando: Ranking de Mercado & Itens mais consumidos
        if any(w in text_lower for w in ["ranking mercado", "ranking de mercado", "o que mais compro", "mais consumidos", "itens mais comprados", "onde mais gasto"]):
            from app.services.market_analytics_service import MarketAnalyticsService
            top_items = MarketAnalyticsService.get_top_consumed_items(db, ws.id, limit=7, sort_by="spent")
            top_stores = MarketAnalyticsService.get_supermarket_ranking(db, ws.id, limit=5)

            lines = ["🏆 *Ranking de Mercado & Consumo*", "───────────────────", "📦 *Produtos com Maior Gasto:*"]
            if not top_items:
                lines.append("_Nenhum produto discriminado registrado ainda._")
            else:
                for idx, it in enumerate(top_items, 1):
                    lines.append(f"*{idx}.* {it['name']} → *{format_currency_br(it['total_spent'])}* ({it['total_quantity']:g} {it['unit']})")

            lines.append("\n🏪 *Supermercados Onde Você Mais Gasta:*")
            if not top_stores:
                lines.append("_Nenhum supermercado registrado ainda._")
            else:
                for idx, st in enumerate(top_stores, 1):
                    lines.append(f"*{idx}.* {st['store_name']} → *{format_currency_br(st['total_spent'])}* ({st['transaction_count']} compras)")

            lines.append("───────────────────")
            lines.append("💡 _Acesse a Aba 8 no Painel Web para ver o Comparador de Preços completo!_")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=get_dashboard_link_keyboard(str(user_tg.id)))
            return

        # Comando: Comparar Preços de Produtos entre Mercados
        if any(w in text_lower for w in ["comparar preco", "comparar preço", "comparar precos", "comparar preços", "preco de", "preço de", "onde é mais barato", "mais barato"]):
            import re
            from app.services.market_analytics_service import MarketAnalyticsService
            search_query = re.sub(r"(?:comparar\s+(?:pre[çc]os?|valores?)|pre[çc]o\s+d[oe]|onde\s+[eé]\s+mais\s+barato|mais\s+barato)\s*", "", text, flags=re.IGNORECASE).strip()
            comparisons = MarketAnalyticsService.get_cross_store_price_comparison(db, ws.id, search_term=search_query if search_query else None)

            if not comparisons:
                await update.message.reply_text(
                    f"🔍 *Nenhum preço encontrado para \"{search_query or 'produtos'}\".*\n\n"
                    f"💡 Ao cadastrar cupons de diferentes supermercados, você poderá comparar os preços aqui!",
                    parse_mode="Markdown"
                )
                return

            lines = [f"🔍 *Comparador de Preços entre Mercados*", "───────────────────"]
            for prod in comparisons[:5]:
                cheap = prod["cheapest_store"]
                exp = prod["most_expensive_store"]
                lines.append(f"🏷️ *{prod['product_name']}* ({prod['category']})")
                lines.append(f"  🟢 *Menor Preço:* {format_currency_br(cheap['price'])}/{cheap['unit']} no *{cheap['store_name']}*")
                if exp:
                    lines.append(f"  🔴 *Mais Caro:* {format_currency_br(exp['price'])}/{exp['unit']} no *{exp['store_name']}*")
                    if prod["diff_pct"] > 0:
                        lines.append(f"  🔥 *Diferença:* +{prod['diff_pct']:.1f}% ({format_currency_br(prod['price_diff'])})")
                lines.append("")

            lines.append("───────────────────")
            lines.append("💡 _Dica: Digite 'comparar precos leite' para buscar um produto específico._")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=get_dashboard_link_keyboard(str(user_tg.id)))
            return

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
    """Processa áudios e notas de voz do Telegram após verificar autenticação"""
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")

        file_obj = await context.bot.get_file(voice.file_id)
        file_ext = ".ogg" if update.message.voice else ".mp3"
        file_path = os.path.join(settings.UPLOAD_DIR, "audio", f"voice_{voice.file_id}{file_ext}")
        await file_obj.download_to_drive(file_path)

        user_tg = update.effective_user
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
    """Processa fotos de comprovantes e notas fiscais com feedback detalhado após verificar autenticação"""
    photos = update.message.photo
    if not photos:
        return

    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")

        photo = photos[-1]  # Maior resolução
        file_obj = await context.bot.get_file(photo.file_id)
        os.makedirs(os.path.join(settings.UPLOAD_DIR, "receipts"), exist_ok=True)
        file_path = os.path.join(settings.UPLOAD_DIR, "receipts", f"receipt_{photo.file_id}.jpg")
        await file_obj.download_to_drive(file_path)

        user_tg = update.effective_user
        user_context = {
            "user_name": user.name,
            "workspace_name": ws.name,
            "workspace_type": ws.type
        }

        parsed = await ai_service.parse_receipt_image(file_path, user_context)

        # Se identificou transações ou ações financeiras com sucesso
        if parsed.intent in ["transaction_record", "account_transfer", "reminder_create", "shopping_action", "vehicle_action", "goal_action"]:
            response_msg, markup = await _apply_parsed_result(db, user, ws, parsed, receipt_url=file_path)
            await update.message.reply_text(
                f"📸 *Comprovante Lido com Sucesso!*\n\n{response_msg}",
                parse_mode="Markdown",
                reply_markup=markup or get_dashboard_link_keyboard(str(user_tg.id))
            )
        else:
            # Falha ou imagem não reconhecida
            error_msg = parsed.friendly_response
            if not error_msg or "Olá!" in error_msg or parsed.intent == "general_chat":
                error_msg = (
                    "❌ *Não consegui ler os dados desta imagem/comprovante.*\n\n"
                    "A foto pode estar embaçada, cortada, com baixa iluminação ou não conter um comprovante legível.\n\n"
                    "💡 *Dicas:*\n"
                    "• Tire uma foto nítida e reta do cupom ou comprovante Pix\n"
                    "• Certifique-se de que o **Valor (R$)** e o **Estabelecimento** estejam visíveis\n"
                    "• Você também pode digitar direto: ex: `Padaria 25 no Pix` ou gravar um áudio 🎙️"
                )
            await update.message.reply_text(
                error_msg,
                parse_mode="Markdown",
                reply_markup=get_dashboard_link_keyboard(str(user_tg.id))
            )
    except Exception as e:
        logger.error(f"Erro ao processar foto: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ *Ocorreu uma falha ao tentar ler a imagem.*\n\n"
            "Não foi possível processar o arquivo enviado. Por favor, tente enviar novamente uma foto mais nítida ou digite o lançamento manualmente.",
            parse_mode="Markdown"
        )
    finally:
        db.close()

async def document_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa arquivos e documentos enviados após verificar autenticação"""
    doc = update.message.document
    if not doc:
        return

    mime_type = doc.mime_type or "application/octet-stream"
    file_name = doc.file_name or f"doc_{doc.file_id}"
    ext = os.path.splitext(file_name)[1].lower()

    # Formatos aceitos para leitura
    supported_images = [".jpg", ".jpeg", ".png", ".webp"]
    supported_docs = [".pdf"]

    if ext not in supported_images and ext not in supported_docs and not mime_type.startswith("image/") and mime_type != "application/pdf":
        await update.message.reply_text(
            f"❌ *Tipo de arquivo não suportado ({ext or mime_type}).*\n\n"
            "O sistema aceita imagens (*JPG, PNG, WebP*) e documentos *PDF* de comprovantes e notas fiscais.\n\n"
            "💡 Por favor, envie o comprovante em formato de foto ou PDF, ou digite o lançamento diretamente.",
            parse_mode="Markdown"
        )
        return

    db = SessionLocal()
    try:
        user, ws = await get_authenticated_bot_user(update, context, db, notify=True)
        if not user or not ws:
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_document")

        os.makedirs(os.path.join(settings.UPLOAD_DIR, "documents"), exist_ok=True)
        file_path = os.path.join(settings.UPLOAD_DIR, "documents", f"doc_{doc.file_id}{ext}")

        file_obj = await context.bot.get_file(doc.file_id)
        await file_obj.download_to_drive(file_path)

        user_tg = update.effective_user
        caption = update.message.caption.strip() if update.message.caption else ""
        user_context = {
            "user_name": user.name,
            "workspace_name": ws.name,
            "workspace_type": ws.type,
            "caption": caption
        }

        if ext in supported_images or mime_type.startswith("image/"):
            parsed = await ai_service.parse_receipt_image(file_path, user_context)
        else:
            parsed = await ai_service.parse_document(file_path, mime_type="application/pdf", user_context=user_context)

        if parsed.intent in ["transaction_record", "account_transfer", "reminder_create", "shopping_action", "vehicle_action", "goal_action"]:
            response_msg, markup = await _apply_parsed_result(db, user, ws, parsed, receipt_url=file_path)
            await update.message.reply_text(
                f"📄 *Arquivo Lido com Sucesso!*\n\n{response_msg}",
                parse_mode="Markdown",
                reply_markup=markup or get_dashboard_link_keyboard(str(user_tg.id))
            )
        else:
            error_msg = parsed.friendly_response
            if not error_msg or "Olá!" in error_msg or parsed.intent == "general_chat":
                error_msg = (
                    "❌ *Não consegui ler os dados deste arquivo/documento.*\n\n"
                    "O documento não contém informações financeiras identificáveis ou está ilegível/protegido.\n\n"
                    "💡 *Dicas:*\n"
                    "• Certifique-se de que o PDF ou imagem é um comprovante ou nota fiscal válida\n"
                    "• O arquivo não deve possuir senha de proteção\n"
                    "• Se preferir, você pode digitar o gasto: ex: `Pix de 150 para João`"
                )
            await update.message.reply_text(
                error_msg,
                parse_mode="Markdown",
                reply_markup=get_dashboard_link_keyboard(str(user_tg.id))
            )
    except Exception as e:
        logger.error(f"Erro ao processar documento: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ *Ocorreu uma falha ao processar o arquivo enviado.*\n\n"
            "Não foi possível extrair as informações. Por favor, tente enviar uma foto nítida ou digite o lançamento no chat.",
            parse_mode="Markdown"
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
        duplicated_items = []
        last_tx = None
        
        for t in parsed.transactions:
            date = datetime.datetime.utcnow() + datetime.timedelta(days=t.date_offset_days)
            
            # Verificação anti-duplicidade
            existing_tx = FinanceService.find_duplicate_transaction(
                db=db,
                workspace_id=ws.id,
                type=t.type,
                amount=t.amount,
                description=t.description,
                transaction_date=date
            )
            
            if existing_tx:
                tipo_icon = "🟢 Entrada" if existing_tx.type == "income" else "🔴 Saída"
                duplicated_items.append(
                    f"{tipo_icon}: *{format_currency_br(existing_tx.amount)}* ({existing_tx.description})\n"
                    f"📅 Data: *{existing_tx.transaction_date.strftime('%d/%m/%Y')}* • 💳 Conta: *{existing_tx.payment_method}*"
                )
                continue

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
                receipt_url=receipt_url,
                items=t.items if hasattr(t, "items") else None
            )
            last_tx = tx
            tipo_icon = "🟢 Entrada" if tx.type == "income" else "🔴 Saída"
            cat_name = tx.category.name if tx.category else "Outros"
            acc_name = tx.payment_method
            item_line = f"{tipo_icon}: *{format_currency_br(tx.amount)}* ({t.description})\n🏷️ Categoria: _{cat_name}_ • 💳 Conta: *{acc_name}*"
            if tx.items_count > 0:
                sample_items = [it.name for it in tx.items[:3]]
                item_line += f"\n🛒 *{tx.items_count} itens incluídos:* " + ", ".join(sample_items) + ("..." if tx.items_count > 3 else "")
            saved_items.append(item_line)

        # Caso todos os itens enviados sejam duplicados
        if not saved_items and duplicated_items:
            dup_msg = (
                f"⚠️ *Lançamento já Cadastrado (Duplicidade Evitada)!*\n\n"
                f"Já identificamos o registro deste lançamento anteriormente:\n\n"
                + "\n\n".join(duplicated_items) + "\n\n"
                f"💡 _Para evitar repetições no seu extrato e saldo, nenhum registro duplicado foi criado._"
            )
            return dup_msg, None

        summary = FinanceService.get_monthly_summary(db, ws.id)
        saldo_emoji = "🟢" if summary["net_balance"] >= 0 else "🔴"
        
        msg_parts = [f"✅ *Lançamento Registrado!*\n\n" + "\n\n".join(saved_items)]
        if duplicated_items:
            msg_parts.append(f"⚠️ *Itens já cadastrados (ignorados para não duplicar):*\n" + "\n\n".join(duplicated_items))
            
        msg_parts.append(
            f"📍 *Perfil:* `{ws.name}`\n"
            f"{saldo_emoji} *Novo Saldo do Mês:* {format_currency_br(summary['net_balance'])}\n\n"
            f"👇 *Selecione ou troque a conta bancária/cartão abaixo:*"
        )
        msg = "\n\n".join(msg_parts)
        accounts = AccountService.get_accounts(db, ws.id)
        markup = get_accounts_selection_keyboard(
            last_tx.id,
            accounts,
            last_tx.account_id,
            has_items=bool(last_tx and last_tx.items_count > 0),
            items_count=last_tx.items_count if last_tx else 0
        ) if last_tx else None
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

        # Verificação anti-duplicidade para contas e boletos
        dup_rem = ReminderService.find_duplicate_reminder(
            db=db,
            workspace_id=ws.id,
            amount=r.amount,
            due_date=due_dt,
            title=r.title
        )
        if dup_rem:
            status_str = "✅ Já Pago" if dup_rem.status == "paid" else "⏰ Pendente na Agenda"
            tipo_str = "🔴 A Pagar" if dup_rem.type == "to_pay" else "🟢 A Receber"
            dup_msg = (
                f"⚠️ *Esta Conta / Boleto já está Cadastrado!*\n\n"
                f"📝 *{dup_rem.title}*\n"
                f"💰 Valor: *{format_currency_br(dup_rem.amount)}*\n"
                f"📅 Vencimento: *{dup_rem.due_date.strftime('%d/%m/%Y')}* ({tipo_str})\n"
                f"📌 Status: *{status_str}*\n\n"
                f"💡 _Para evitar duplicidade, o boleto não foi registrado novamente na sua agenda._"
            )
            return dup_msg, None

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
            price_str = f" → ~{format_currency_br(item.estimated_price * item.quantity)}" if item.estimated_price > 0 else ""
            added.append(f"• *{item.name}* ({item.quantity:g} {item.unit}){price_str}")

        total_forecast = s_list.total_estimated
        forecast_str = f"\n\n💰 *Total Estimado da Compra:* {format_currency_br(total_forecast)}" if total_forecast > 0 else ""
        return f"🛒 *Itens adicionados à Lista de Mercado:*\n\n" + "\n".join(added) + forecast_str + "\n\n💡 _Os valores estimados foram baseados no histórico das suas compras anteriores._", None

    # 6. Troca de perfil
    elif intent == "profile_switch" and parsed.target_profile:
        new_ws = FinanceService.switch_workspace(db, user, parsed.target_profile)
        return f"🔄 *Perfil alternado para:* `{new_ws.name}`\nTodos os próximos lançamentos serão registrados nesta conta.", None

    # Resposta amigável padrão
    return parsed.friendly_response, None
