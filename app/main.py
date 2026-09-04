import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database import init_db
from app.web.routes import router as web_router
from app.bot.bot_instance import create_bot_app
from app.services.reminder_service import ReminderService

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("ControleGastos")

scheduler = AsyncIOScheduler()
bot_application = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_application

    logger.info("Iniciando Sistema de Controle Financeiro Inteligente...")
    # 1. Inicializa tabelas do banco de dados
    init_db()

    # 2. Inicializa o Bot do Telegram
    bot_application = create_bot_app()
    if bot_application:
        try:
            await bot_application.initialize()
            await bot_application.start()
            await bot_application.updater.start_polling(drop_pending_updates=True)
            logger.info("Telegram Bot iniciado e ouvindo mensagens...")
        except Exception as e:
            logger.error(f"Erro ao iniciar polling do Telegram Bot: {e}")
    else:
        logger.warning("Bot do Telegram não iniciado. Verifique o TELEGRAM_BOT_TOKEN no .env")

    # 3. Inicia o agendador de lembretes e contas
    try:
        scheduler.add_job(
            ReminderService.check_and_send_due_reminders,
            "interval",
            minutes=30,
            args=[bot_application],
            id="due_reminders_check",
            replace_existing=True
        )
        scheduler.start()
        logger.info("Agendador APScheduler iniciado (verificação a cada 30min).")
    except Exception as e:
        logger.error(f"Erro ao iniciar APScheduler: {e}")

    yield

    # Shutdown
    logger.info("Encerrando serviços...")
    if scheduler.running:
        scheduler.shutdown()
    if bot_application and bot_application.updater and bot_application.updater.running:
        await bot_application.updater.stop()
        await bot_application.stop()
        await bot_application.shutdown()
    logger.info("Serviços finalizados.")

# Criação da Aplicação FastAPI
app = FastAPI(
    title="Sistema de Gestão Financeira Inteligente (Telegram + IA)",
    description="Plataforma completa de finanças com bot no Telegram, NLP Multimodal e Dashboard Web",
    version="1.0.0",
    lifespan=lifespan
)

# Monta arquivos estáticos (CSS, JS, Imagens)
static_dir = os.path.join(os.path.dirname(__file__), "web", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Inclui rotas do Dashboard Web
app.include_router(web_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
