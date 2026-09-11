import logging
from typing import Optional, Tuple
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session
from app.models import User, Workspace
from app.services.auth_service import AuthService
from app.services.finance_service import FinanceService
from app.bot.keyboards import get_main_reply_keyboard

logger = logging.getLogger(__name__)

async def get_authenticated_bot_user(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    db: Session,
    notify: bool = True
) -> Tuple[Optional[User], Optional[Workspace]]:
    """
    Verifica se o usuário do Telegram está devidamente autenticado e ativo.
    Se não estiver autenticado e notify=True, envia a mensagem solicitando a senha.
    Retorna (user, workspace) se autenticado, ou (None, None) caso contrário.
    """
    user_tg = update.effective_user
    if not user_tg:
        return None, None

    is_auth, user, status_code = AuthService.verify_telegram_auth(db, str(user_tg.id))

    if is_auth and user:
        # Usuário autenticado e ativo
        # Garante workspace ativo
        if not user.current_workspace_id or not user.current_workspace:
            _, ws = FinanceService.get_or_create_user(db, str(user_tg.id), user_tg.full_name, user_tg.username)
        else:
            ws = user.current_workspace
        return user, ws

    if not notify:
        return None, None

    # Tratamento de status não autenticado
    if status_code == "inactive":
        msg = (
            "⛔ *Acesso Bloqueado*\n\n"
            "Sua conta de usuário foi inativada pelo administrador do sistema.\n"
            "Entre em contato com o suporte ou administrador para reativar seu acesso."
        )
        if update.callback_query:
            await update.callback_query.answer("⛔ Usuário inativo no sistema.", show_alert=True)
            await update.callback_query.message.reply_text(msg, parse_mode="Markdown")
        elif update.message:
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return None, None

    if status_code == "unauthenticated" and user:
        msg = (
            f"🔒 *Autenticação Necessária*\n\n"
            f"Olá, *{user.name or user.username}*!\n"
            f"Para sua segurança, informe sua **senha de acesso** (a mesma cadastrada na Web) para desbloquear o assistente no Telegram.\n\n"
            f"👉 *Basta digitar sua senha aqui no chat* ou enviar:\n"
            f"`/login {user.username or 'seu_usuario'} sua_senha`"
        )
        if update.callback_query:
            await update.callback_query.answer("🔒 Autenticação necessária. Digite sua senha no chat.", show_alert=True)
            await update.callback_query.message.reply_text(msg, parse_mode="Markdown")
        elif update.message:
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return None, None

    # unregistered (ainda sem vínculo)
    msg = (
        f"🔒 *Acesso Restrito ao Sistema*\n\n"
        f"Olá, *{user_tg.first_name}*! Este assistente é de uso exclusivo para usuários cadastrados no Sistema de Controle Financeiro.\n\n"
        f"Se você já possui cadastro na Web, informe seu **Usuário** e **Senha** para liberar o acesso:\n\n"
        f"👉 Envie no formato:\n"
        f"`/login seu_usuario sua_senha`\n\n"
        f"_(Exemplo: `/login admin MinhaSenha123`)_"
    )
    if update.callback_query:
        await update.callback_query.answer("🔒 Acesso restrito. Faça login com /login usuario senha", show_alert=True)
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown")
    elif update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

    return None, None
