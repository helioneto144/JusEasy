"""Gmail IMAP client — captura emails OAB-ES da conta Gmail do usuário.

Login via App Password (precisa 2FA ativado em myaccount.google.com).
Lê emails UNSEEN com label especifica, retorna lista de dicts.
"""
import logging
from typing import List, Dict
from imap_tools import MailBox, AND
from imap_tools.errors import MailboxLoginError

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def fetch_oab_es_emails(mark_seen: bool = True, limit: int = 50) -> List[Dict]:
    """Busca emails UNSEEN com a label configurada.

    Retorna lista no formato esperado pelo pipeline:
        [{"from": str, "subject": str, "html": str, "text": str,
          "date": str (ISO), "uid": str}]

    Se mark_seen=True, marca como lido após retornar (evita reprocessamento).
    """
    if not settings.gmail_user or not settings.gmail_app_password:
        logger.warning("gmail_imap: credenciais Gmail nao configuradas")
        return []

    emails = []
    try:
        with MailBox(settings.gmail_imap_host).login(
            settings.gmail_user,
            settings.gmail_app_password,
            initial_folder=settings.gmail_imap_label or "INBOX"
        ) as mailbox:
            messages = mailbox.fetch(AND(seen=False), limit=limit, mark_seen=mark_seen)
            for msg in messages:
                emails.append({
                    "from": msg.from_ or "",
                    "from_name": (msg.from_values.name if msg.from_values else "") or "",
                    "subject": msg.subject or "",
                    "html": msg.html or "",
                    "text": msg.text or "",
                    "date": msg.date.isoformat() if msg.date else "",
                    "uid": msg.uid or "",
                    "message_id": msg.headers.get("message-id", [""])[0] if msg.headers else "",
                })
        logger.info(f"gmail_imap: {len(emails)} email(s) coletado(s)")
    except MailboxLoginError as e:
        logger.error(f"gmail_imap: falha de login (App Password incorreta?): {e}")
    except Exception as e:
        logger.error(f"gmail_imap: erro: {e}")

    return emails


def test_connection() -> dict:
    """Smoke test — usado pelo healthcheck/troubleshoot."""
    if not settings.gmail_user or not settings.gmail_app_password:
        return {"ok": False, "reason": "credenciais nao configuradas"}
    try:
        with MailBox(settings.gmail_imap_host).login(
            settings.gmail_user,
            settings.gmail_app_password,
        ) as mailbox:
            folders = [f.name for f in mailbox.folder.list()]
            return {
                "ok": True,
                "user": settings.gmail_user,
                "label_alvo": settings.gmail_imap_label,
                "label_existe": settings.gmail_imap_label in folders,
                "folders_count": len(folders),
            }
    except MailboxLoginError as e:
        return {"ok": False, "reason": f"login falhou: {e}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
