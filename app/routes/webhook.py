"""Webhook endpoints — receives external events (Cloudflare Email Worker, etc)."""
import logging
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database.supabase_client import supabase

settings = get_settings()
router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/webhook/email")
async def receive_email(request: Request, background_tasks: BackgroundTasks):
    """Receives forwarded emails from Cloudflare Email Worker.

    Auth: X-Webhook-Secret header must match settings.webhook_secret.
    Stores raw email in `emails_recebidos` for later processing.
    """
    # ── Auth ──
    secret = request.headers.get("X-Webhook-Secret", "")
    if not settings.webhook_secret:
        logger.error("webhook/email: WEBHOOK_SECRET nao configurado no servidor")
        raise HTTPException(503, "Webhook nao configurado")
    if secret != settings.webhook_secret:
        client = request.client.host if request.client else "?"
        logger.warning(f"webhook/email: auth falhou de {client}")
        raise HTTPException(403, "Unauthorized")

    # ── Payload ──
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    from_addr = (payload.get("from") or "")[:255]
    subject = (payload.get("subject") or "")[:500]
    body_html = payload.get("html") or ""
    body_text = payload.get("text") or ""
    received_at_source = (payload.get("date") or "")[:64]

    # ── Persist ──
    try:
        result = supabase.table("emails_recebidos").insert({
            "from_addr": from_addr,
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
            "received_at_source": received_at_source,
            "processed": False,
        }).execute()
    except Exception as e:
        logger.error(f"webhook/email: erro ao salvar: {e}")
        raise HTTPException(500, "Erro ao persistir email")

    email_id = result.data[0]["id"] if result.data else None
    logger.info(f"webhook/email: id={email_id} from={from_addr} subject={subject[:80]}")

    # ── Process (Fase 3) ──
    if settings.oab_es_enabled and email_id:
        from app.scheduler.jobs import process_single_email
        background_tasks.add_task(process_single_email, email_id)

    return JSONResponse({"status": "received", "id": email_id})
