import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.config import get_settings
from app.bot.bot import bot
from app.routes import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
scheduler = AsyncIOScheduler()
event_loop = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global event_loop
    event_loop = asyncio.get_running_loop()
    
    logger.info("Starting application...")
    await bot.initialize()
    await bot.start()
    logger.info("Bot started")

    tz = "America/Sao_Paulo"
    
    scheduler.add_job(
        run_check_intimacoes,
        CronTrigger(hour="8,12,16", timezone=tz),
        id="check_intimacoes",
        name="Verificar intimações AASP"
    )
    scheduler.add_job(
        run_check_prazos,
        CronTrigger(hour="7,18", timezone=tz),
        id="check_prazos",
        name="Verificar prazos"
    )
    scheduler.add_job(
        run_resumo_diario,
        CronTrigger(hour="9", timezone=tz),
        id="resumo_diario",
        name="Resumo diário"
    )
    scheduler.start()
    logger.info(f"Scheduler started with timezone {tz}")

    yield

    scheduler.shutdown()
    await bot.stop()


def run_check_intimacoes():
    from app.scheduler.jobs import check_intimacoes
    logger.info("Job: check_intimacoes iniciado")
    if not event_loop:
        logger.error("Job: check_intimacoes - event_loop não disponível")
        return
    try:
        asyncio.run_coroutine_threadsafe(check_intimacoes(), event_loop).result(timeout=120)
        logger.info("Job: check_intimacoes concluído")
    except Exception as e:
        logger.error(f"Job: check_intimacoes erro: {e}")


def run_check_prazos():
    from app.scheduler.jobs import check_prazos
    logger.info("Job: check_prazos iniciado")
    if not event_loop:
        logger.error("Job: check_prazos - event_loop não disponível")
        return
    try:
        asyncio.run_coroutine_threadsafe(check_prazos(), event_loop).result(timeout=60)
        logger.info("Job: check_prazos concluído")
    except Exception as e:
        logger.error(f"Job: check_prazos erro: {e}")


def run_resumo_diario():
    from app.scheduler.jobs import resumo_diario
    logger.info("Job: resumo_diario iniciado")
    if not event_loop:
        logger.error("Job: resumo_diario - event_loop não disponível")
        return
    try:
        asyncio.run_coroutine_threadsafe(resumo_diario(), event_loop).result(timeout=60)
        logger.info("Job: resumo_diario concluído")
    except Exception as e:
        logger.error(f"Job: resumo_diario erro: {e}")


app = FastAPI(
    title="JusEasy - Gestão de Processos",
    description="Sistema pessoal de gestão de prazos e processos jurídicos",
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.state.templates = templates

app.include_router(web.router)


@app.get("/api")
async def api_root():
    return {"status": "running", "service": "Oracle"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/check-intimacoes")
async def trigger_check():
    from app.scheduler.jobs import check_intimacoes
    await check_intimacoes()
    return {"status": "checked"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
