from telegram import Update
from telegram.ext import ContextTypes
from app.database import SessionLocal
from app.services.finance_service import FinanceService
from app.bot.keyboards import get_main_reply_keyboard, get_dashboard_link_keyboard

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start inicial do Bot com suporte a link de convite direto"""
    user_tg = update.effective_user
    db = SessionLocal()
    try:
        user, ws = FinanceService.get_or_create_user(
            db=db,
            telegram_id=str(user_tg.id),
            name=user_tg.full_name or user_tg.first_name,
            username=user_tg.username
        )

        joined_ws = None
        if context.args and len(context.args) > 0:
            arg_code = context.args[0].replace("convite_", "").replace("join_", "").strip().upper()
            if arg_code:
                joined_ws = FinanceService.join_shared_workspace(db, user, arg_code)

        if joined_ws:
            msg = (
                f"🎉 *Sucesso! Você ingressou no grupo/perfil:* `{joined_ws.name}`\n\n"
                f"👤 *Seu Usuário:* {user_tg.first_name} (@{user_tg.username or user_tg.id})\n"
                f"📍 *Perfil Ativo:* `{joined_ws.name}` (Tipo: `{joined_ws.type.upper()}`)\n\n"
                f"A partir de agora, todos os lançamentos que você enviar aqui no bot "
                f"serão registrados diretamente nesta conta compartilhada e sincronizados no painel Web!\n\n"
                f"💡 *Exemplo de lançamento:* Envie _\"Almoço 45 no dinheiro\"_ ou grave um áudio!"
            )
        else:
            msg = (
                f"👋 *Olá, {user_tg.first_name}! Bem-vindo ao seu Assistente Financeiro Inteligente.*\n\n"
                f"Eu registro e organizo automaticamente suas finanças direto aqui no Telegram com IA!\n\n"
                f"📍 *Perfil Ativo:* `{ws.name}`\n\n"
                f"💡 *Como usar:*\n"
                f"• *Texto livre:* _\"Gastei 45 no almoço no cartão\"_\n"
                f"• *Receitas:* _\"Recebi 3500 de salário no pix\"_\n"
                f"• *Áudios de voz:* _Basta gravar um áudio me contando seus gastos!_\n"
                f"• *Fotos/Recibos:* _Envie foto de comprovante ou nota fiscal_\n"
                f"• *Lembretes:* _\"Lembrar de pagar internet 120 dia 10\"_\n"
                f"• *Metas:* _\"Guardei 200 pra viagem\"_\n"
                f"• *Veículo:* _\"Troquei óleo 250 aos 50000 km\"_\n\n"
                f"Use o menu abaixo ou envie qualquer mensagem para começar!"
            )

        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard()
        )
    finally:
        db.close()

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ajuda"""
    msg = (
        f"📖 *Guia de Comandos e Recursos:*\n\n"
        f"🔹 *Registro Inteligente:* Envie texto, áudio ou foto de notas fiscais.\n"
        f"🔹 `/saldo` - Veja o resumo de entradas, saídas e saúde financeira do mês.\n"
        f"🔹 `/extrato` - Últimas 10 transações registradas.\n"
        f"🔹 `/perfil` - Alterne entre conta Pessoal (PF) e Empresa (PJ).\n"
        f"🔹 `/lembretes` - Veja e cadastre contas a pagar/receber.\n"
        f"🔹 `/metas` - Acompanhe suas caixinhas e objetivos de economia.\n"
        f"🔹 `/veiculo` - Histórico de manutenção e alertas de troca de óleo.\n"
        f"🔹 `/mercado` - Checklist interativo de supermercado.\n"
        f"🔹 `/painel` - Acesse o Dashboard Web com gráficos interativos e exportação."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
