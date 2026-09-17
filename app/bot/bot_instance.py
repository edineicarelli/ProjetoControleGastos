import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from app.config import settings
from app.bot.handlers.start import start_handler, help_handler
from app.bot.handlers.commands import (
    saldo_handler,
    extrato_handler,
    perfil_handler,
    contas_handler,
    lembretes_handler,
    metas_handler,
    veiculo_handler,
    mercado_handler,
    painel_handler,
    entrar_handler,
    zerar_handler,
    login_handler,
    senha_handler,
    logout_handler,
    cupom_handler,
    despesas_handler,
    receitas_handler
)
from app.bot.handlers.text_voice_photo import (
    text_message_handler,
    voice_message_handler,
    photo_message_handler,
    document_message_handler
)
from app.bot.handlers.callbacks import callback_query_handler

logger = logging.getLogger(__name__)

def create_bot_app():
    """Cria e configura a instância do aplicativo Telegram Bot"""
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN == "SEU_TELEGRAM_BOT_TOKEN_AQUI":
        logger.warning("TELEGRAM_BOT_TOKEN não foi configurado no arquivo .env!")
        return None

    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Comandos de Autenticação e Senha
    app.add_handler(CommandHandler("senha", senha_handler))
    app.add_handler(CommandHandler("definirsenha", senha_handler))
    app.add_handler(CommandHandler("login", login_handler))
    app.add_handler(CommandHandler("sair", logout_handler))
    app.add_handler(CommandHandler("logout", logout_handler))
    app.add_handler(CommandHandler("bloquear", logout_handler))

    # Comandos básicos
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("entrar", entrar_handler))
    app.add_handler(CommandHandler("join", entrar_handler))
    app.add_handler(CommandHandler("ajuda", help_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("saldo", saldo_handler))
    app.add_handler(CommandHandler("extrato", extrato_handler))
    app.add_handler(CommandHandler("contas", contas_handler))
    app.add_handler(CommandHandler("perfil", perfil_handler))
    app.add_handler(CommandHandler("lembretes", lembretes_handler))
    app.add_handler(CommandHandler("metas", metas_handler))
    app.add_handler(CommandHandler("veiculo", veiculo_handler))
    app.add_handler(CommandHandler("mercado", mercado_handler))
    app.add_handler(CommandHandler("painel", painel_handler))
    app.add_handler(CommandHandler("zerar", zerar_handler))
    app.add_handler(CommandHandler("zerarconta", zerar_handler))
    app.add_handler(CommandHandler("limpar", zerar_handler))
    app.add_handler(CommandHandler("cupom", cupom_handler))
    app.add_handler(CommandHandler("cupons", cupom_handler))
    app.add_handler(CommandHandler("itens", cupom_handler))
    app.add_handler(CommandHandler("notafiscal", cupom_handler))
    app.add_handler(CommandHandler("nota", cupom_handler))
    app.add_handler(CommandHandler("produtos", cupom_handler))
    app.add_handler(CommandHandler("despesas", despesas_handler))
    app.add_handler(CommandHandler("despesa", despesas_handler))
    app.add_handler(CommandHandler("gastos", despesas_handler))
    app.add_handler(CommandHandler("gastosmes", despesas_handler))
    app.add_handler(CommandHandler("despesasmes", despesas_handler))
    app.add_handler(CommandHandler("despesasconta", despesas_handler))
    app.add_handler(CommandHandler("gastosconta", despesas_handler))
    app.add_handler(CommandHandler("receitas", receitas_handler))
    app.add_handler(CommandHandler("receita", receitas_handler))
    app.add_handler(CommandHandler("entradas", receitas_handler))
    app.add_handler(CommandHandler("ganhos", receitas_handler))
    app.add_handler(CommandHandler("receitasmes", receitas_handler))
    app.add_handler(CommandHandler("receitasconta", receitas_handler))

    # Handlers Multimodais (Texto, Voz, Foto, Documentos)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_message_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_message_handler))

    # Callbacks de Botões Inline
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # Handler Global de Erros
    async def global_error_handler(update: object, context):
        logger.error(f"Erro capturado pelo bot: {context.error}", exc_info=context.error)

    app.add_error_handler(global_error_handler)

    return app
