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
from app.routes import web, webhook

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
    # OAB-ES envia entre 02h-03h America/Sao_Paulo (validado em emails reais).
    # Rodamos as 04h, 07h e 10h pra pegar o do dia + fallback.
    scheduler.add_job(
        run_check_gmail_oab_es,
        CronTrigger(hour="4,7,10", minute="0", timezone=tz),
        id="check_gmail_oab_es",
        name="Coletar emails OAB-ES via Gmail IMAP"
    )
    scheduler.start()
    logger.info(f"Scheduler started with timezone {tz}")

    yield

    scheduler.shutdown()
    await bot.stop()


def run_check_intimacoes():
    if not settings.aasp_enabled:
        logger.info("Job: check_intimacoes pulado (aasp_enabled=false)")
        return
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


def run_check_gmail_oab_es():
    from app.scheduler.jobs import check_gmail_oab_es
    logger.info("Job: check_gmail_oab_es iniciado")
    if not event_loop:
        logger.error("Job: check_gmail_oab_es - event_loop nao disponivel")
        return
    try:
        count = asyncio.run_coroutine_threadsafe(check_gmail_oab_es(), event_loop).result(timeout=60)
        logger.info(f"Job: check_gmail_oab_es concluido — {count} email(s)")
    except Exception as e:
        logger.error(f"Job: check_gmail_oab_es erro: {e}")


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
app.include_router(webhook.router)


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


@app.post("/api/check-gmail")
async def trigger_gmail_check():
    """Dispara manualmente a coleta de emails OAB-ES (debug/teste)."""
    from app.scheduler.jobs import check_gmail_oab_es
    count = await check_gmail_oab_es()
    return {"status": "checked", "emails_novos": count}


@app.get("/api/gmail-test")
async def gmail_smoke_test():
    """Testa conexao IMAP com Gmail (sem ler emails)."""
    from app.services.gmail_imap import test_connection
    return test_connection()


@app.post("/api/admin/parse-test")
async def admin_parse_test(email_id: str = ""):
    """Admin: roda apenas o parser num email_recebido (sem INSERT/notify).

    Se email_id vazio, parseia o primeiro email com publicacao do banco.
    Retorna o resultado do parser pra validacao manual.
    """
    from app.services.email_parser import parse_oab_es_email
    from app.database.supabase_client import supabase

    if email_id:
        resp = supabase.table("emails_recebidos").select("*").eq("id", email_id).limit(1).execute()
    else:
        resp = supabase.table("emails_recebidos").select("*").like(
            "subject", "Public. 1.%"
        ).order("received_at_source").limit(1).execute()

    if not resp.data:
        return {"error": "nenhum email encontrado"}

    email = resp.data[0]
    intimacoes = parse_oab_es_email(
        email.get("body_html") or "",
        email.get("body_text") or "",
        email.get("subject") or "",
    )
    return {
        "email": {
            "id": email["id"],
            "subject": email["subject"],
            "received_at_source": email.get("received_at_source"),
        },
        "intimacoes_count": len(intimacoes),
        "intimacoes": intimacoes,
    }


@app.post("/api/admin/reprocess-emails")
async def admin_reprocess_emails(only_with_publications: bool = True, limit: int = 50):
    """Admin: reprocessa emails ja salvos em emails_recebidos.

    Util pra testar parser nos 4 emails 'Public. 1.' ja coletados,
    ou pra reprocessar caso algum tenha dado parse_error.
    """
    from app.scheduler.jobs import process_email_to_intimacoes, _has_publications
    from app.database.supabase_client import supabase

    q = supabase.table("emails_recebidos").select(
        "id,subject,body_html,body_text"
    ).eq("processed", False).limit(limit)
    if only_with_publications:
        q = q.not_.like("subject", "Public. 0.%")
    resp = q.execute()

    results = []
    for email in resp.data or []:
        if only_with_publications and not _has_publications(email.get("subject", ""), email.get("body_html", "")):
            continue
        try:
            count = await process_email_to_intimacoes(
                email["id"], email["body_html"], email.get("body_text") or "", email.get("subject") or ""
            )
            results.append({"email_id": email["id"], "subject": email["subject"], "intimacoes": count})
        except Exception as e:
            results.append({"email_id": email["id"], "error": str(e)})
    return {"processed": len(results), "results": results}


@app.post("/api/admin/gmail-fetch-by-subject")
async def admin_fetch_by_subject(subject: str):
    """Admin: busca emails ja lidos por subject e salva em emails_recebidos.

    Util pra trazer amostras antigas. Dedup por message_id evita duplicar.
    Ex: ?subject=Public. 1.
    """
    from app.services.gmail_imap import fetch_by_subject
    from app.database.supabase_client import supabase

    emails = fetch_by_subject(subject, mark_seen=False, limit=50)
    saved = 0
    for email in emails:
        mid = email.get("message_id") or ""
        if mid:
            existing = supabase.table("emails_recebidos").select("id").eq(
                "message_id", mid
            ).limit(1).execute()
            if existing.data:
                continue
        supabase.table("emails_recebidos").insert({
            "from_addr": (email.get("from") or "")[:255],
            "subject": (email.get("subject") or "")[:500],
            "body_html": email.get("html") or "",
            "body_text": email.get("text") or "",
            "received_at_source": email.get("date") or "",
            "message_id": mid[:255],
            "imap_uid": (email.get("uid") or "")[:64],
            "processed": False,
        }).execute()
        saved += 1
    return {"status": "ok", "encontrados": len(emails), "salvos_novos": saved}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
