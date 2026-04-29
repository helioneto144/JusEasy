import asyncio
import hashlib
import logging
import re
from datetime import date, timedelta
from app.database.supabase_client import supabase
from app.services.aasp import aasp_client, parse_dados_processo
from app.services.ai_service import summarize_intimacao
from app.bot.bot import bot
from app.bot.keyboards import kb_intimacao, kb_tarefa
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def extract_processo_numero(text: str) -> str | None:
    pattern = r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}'
    match = re.search(pattern, text)
    return match.group(0) if match else None


def generate_hash(conteudo: str, data: str) -> str:
    return hashlib.sha256(f"{conteudo}{data}".encode()).hexdigest()[:64]


def fmt_data(data_str: str) -> str:
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(str(data_str)[:10])
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(data_str)[:10]


async def notify_nova_intimacao(intimacao_dict: dict, data_disp: date, db_id: str):
    numero = intimacao_dict.get('processo')
    conteudo = intimacao_dict.get('conteudo', '')[:500].replace('<', '&lt;').replace('>', '&gt;')
    diario = intimacao_dict.get('diario', '') or ""

    msg = (
        f"🔔 <b>NOVA INTIMAÇÃO DISPONÍVEL</b>\n\n"
        f"📅 <b>Data:</b> {data_disp.strftime('%d/%m/%Y')}\n"
        f"📰 <b>Diário:</b> {diario}\n"
    )

    if numero:
        msg += f"📋 <b>Processo:</b> <code>{numero}</code>\n"

    msg += f"📝 <b>Conteúdo:</b>\n{conteudo}…\n"

    try:
        await bot.app.bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=msg,
            parse_mode="HTML",
            reply_markup=kb_intimacao(intimacao_id=db_id, processo_numero=numero)
        )
    except Exception as e:
        logger.error(f"Erro ao enviar notificação da intimação {db_id}: {e}")


async def check_intimacoes():
    logger.info("Iniciando verificação de intimações AASP...")
    try:
        jornais = await aasp_client.get_jornais_com_intimacoes(qtde_dias=3)
        logger.info(f"Encontrados {len(jornais) if jornais else 0} jornais com intimações")

        if not jornais:
            logger.info("Nenhum jornal encontrado")
            return 0

        count = 0

        for jornal_data in jornais:
            data_str = jornal_data.get("dataDisponibilizacao_Publicacao", "")
            if data_str:
                data_date = date.fromisoformat(data_str[:10])
            else:
                continue

            intimacoes = await aasp_client.get_intimacoes(data=data_date)
            logger.info(f"Data {data_date}: {len(intimacoes)} intimações")

            if not intimacoes:
                continue

            # Batch: calcular todos os hashes do lote e buscar existentes de uma vez
            hashes_lote = [generate_hash(item.get("conteudo", ""), data_str) for item in intimacoes]
            existing_resp = supabase.table("intimacoes").select("hash_conteudo").in_("hash_conteudo", hashes_lote).execute()
            existing_set = {r["hash_conteudo"] for r in existing_resp.data}

            for item, hash_conteudo in zip(intimacoes, hashes_lote):
                if hash_conteudo in existing_set:
                    continue

                conteudo = item.get("conteudo", "")
                numero_processo = item.get("numero_processo") or extract_processo_numero(conteudo)
                processo_id = None

                if numero_processo:
                    result = supabase.table("processos").select("id").eq("numero", numero_processo).execute()

                    if result.data:
                        processo_id = result.data[0]["id"]
                    else:
                        dados = parse_dados_processo(conteudo)
                        new_proc = supabase.table("processos").insert({
                            "numero": numero_processo,
                            "vara": dados.get("vara"),
                            "comarca": dados.get("comarca"),
                            "partes": dados.get("partes", {"autor": [], "reu": []}),
                        }).execute()
                        if new_proc.data:
                            processo_id = new_proc.data[0]["id"]

                intimacao_data = {
                    "processo_id": processo_id,
                    "data_disponibilizacao": str(data_date),
                    "conteudo": conteudo,
                    "diario_oficial": item.get("diario_oficial"),
                    "hash_conteudo": hash_conteudo,
                    "lida": False
                }
                res = supabase.table("intimacoes").insert(intimacao_data).execute()
                count += 1

                if res.data:
                    db_id = res.data[0]["id"]
                    await notify_nova_intimacao({
                        "processo": numero_processo,
                        "conteudo": conteudo,
                        "diario": intimacao_data["diario_oficial"],
                    }, data_date, db_id)

                    # Resumo IA via Groq (só se configurado)
                    if settings.groq_api_key:
                        resumo_ia = await summarize_intimacao(conteudo)
                        if resumo_ia:
                            await bot.send_message(f"🤖 <b>Resumo IA:</b>\n{resumo_ia}", parse_mode="HTML")

                    await asyncio.sleep(1)

        if count > 0:
            logger.info(f"Processadas {count} novas intimações do AASP.")

        return count

    except Exception as e:
        logger.error(f"Erro ao verificar intimações: {e}", exc_info=True)
        return 0


async def check_intimacoes_periodo(dias: int = 10):
    try:
        count = 0
        hoje = date.today()

        for i in range(dias):
            data = hoje - timedelta(days=i)

            try:
                intimacoes = await aasp_client.get_intimacoes(data=data)
            except Exception as e:
                logger.error(f"Erro ao buscar {data}: {e}")
                continue

            for item in intimacoes:
                conteudo = item.get("conteudo", "")
                data_str = str(data)
                hash_conteudo = generate_hash(conteudo, data_str)

                existing = supabase.table("intimacoes").select("id").eq("hash_conteudo", hash_conteudo).execute()
                if existing.data:
                    continue

                numero_processo = item.get("numero_processo") or extract_processo_numero(conteudo)
                processo_id = None

                if numero_processo:
                    result = supabase.table("processos").select("id").eq("numero", numero_processo).execute()

                    if result.data:
                        processo_id = result.data[0]["id"]
                    else:
                        dados = parse_dados_processo(conteudo)
                        new_proc = supabase.table("processos").insert({
                            "numero": numero_processo,
                            "vara": dados.get("vara"),
                            "comarca": dados.get("comarca"),
                            "partes": dados.get("partes", {"autor": [], "reu": []}),
                        }).execute()
                        if new_proc.data:
                            processo_id = new_proc.data[0]["id"]

                intimacao_data = {
                    "processo_id": processo_id,
                    "data_disponibilizacao": str(data),
                    "conteudo": conteudo,
                    "diario_oficial": item.get("diario_oficial"),
                    "hash_conteudo": hash_conteudo,
                    "lida": False
                }
                supabase.table("intimacoes").insert(intimacao_data).execute()
                count += 1

        return count

    except Exception as e:
        logger.error(f"Erro ao importar intimações: {e}", exc_info=True)
        return 0


async def check_prazos():
    hoje = date.today()
    limite = hoje + timedelta(days=3)

    response = supabase.table("tarefas").select("*").eq("concluida", False).gte("data_vencimento", str(hoje)).lte("data_vencimento", str(limite)).eq("notificado", False).execute()
    tarefas = response.data

    if not tarefas:
        return

    await bot.send_message("⚠️ <b>Prazos Próximos (próximos 3 dias):</b>", parse_mode="HTML")

    for tarefa in tarefas:
        try:
            prioridade = tarefa.get("prioridade", "media")
            prioridade_emoji = {"urgente": "🔴", "alta": "🟠", "media": "🟡", "baixa": "🟢"}.get(prioridade, "⚪")

            msg = (
                f"{prioridade_emoji} <b>{tarefa.get('titulo')}</b>\n"
                f"📅 Vencimento: {fmt_data(tarefa.get('data_vencimento', ''))}"
            )
            await bot.app.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=msg,
                parse_mode="HTML",
                reply_markup=kb_tarefa(tarefa["id"])
            )
            supabase.table("tarefas").update({"notificado": True}).eq("id", tarefa["id"]).execute()
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Erro enviando notif de prazo {tarefa.get('id')}: {e}")


async def resumo_diario(force: bool = False):
    # Envia de manhãzinha (09:00) — somente se houver algo relevante (ou force=True)
    from app.database.supabase_client import get_stats, get_tarefas_por_data
    stats = await get_stats()

    hoje = date.today()
    tars_hoje = await get_tarefas_por_data(hoje)

    nlidas = stats['intimacoes_nao_lidas']
    urgentes = stats['tarefas_urgentes']

    if not force and not tars_hoje and nlidas == 0 and urgentes == 0:
        logger.info("resumo_diario: nada relevante para reportar, pulando envio.")
        return

    text = (
        f"☕ <b>Bom dia, Doutor(a)!</b>\n\n"
        f"📅 Hoje é {hoje.strftime('%d/%m/%Y')}\n"
    )

    if tars_hoje:
        prioridade_emoji = {"urgente": "🔴", "alta": "🟠", "media": "🟡", "baixa": "🟢"}
        text += f"\n📌 <b>Tarefas para hoje ({len(tars_hoje)}):</b>\n"
        for t in tars_hoje:
            p = prioridade_emoji.get(t.get("prioridade", "media"), "⚪")
            text += f" {p} {t.get('titulo', '')}\n"
    else:
        text += "\n✅ Sem tarefas vencendo hoje.\n"

    if nlidas > 0 or urgentes > 0:
        text += "\n⚠️ <b>Atenção:</b>\n"
        if nlidas > 0:
            text += f"Você tem {nlidas} intimações não lidas (/intimacoes).\n"
        if urgentes > 0:
            text += f"Existem {urgentes} prazos extremamente urgentes (/prazos).\n"

    await bot.send_message(text, parse_mode="HTML")


# ─────────────────────────────────────────────
# Gmail IMAP — captura de emails OAB-ES
# ─────────────────────────────────────────────

# Subjects "Public. 0." = zero publicacoes — nao processar.
_SUBJECT_ZERO_PUB = re.compile(r'\bPublic\.\s*0\.', re.IGNORECASE)


def _has_publications(subject: str, body_html: str) -> bool:
    """Retorna True se o email tem >= 1 publicacao."""
    if subject and _SUBJECT_ZERO_PUB.search(subject):
        return False
    if "Não foi localizada qualquer publicação" in (body_html or ""):
        return False
    return True


async def check_gmail_oab_es():
    """Busca emails UNSEEN com label OAB-ES e processa.

    Fluxo:
      1. IMAP fetch de novos emails
      2. Salva cru em emails_recebidos (auditoria)
      3. Se tem publicacoes (Public. N. com N >= 1):
         - Parse com email_parser
         - Para cada intimacao: dedup, INSERT, notify Telegram, AI summary
    """
    if not settings.gmail_user or not settings.gmail_app_password:
        logger.info("check_gmail_oab_es: credenciais Gmail nao configuradas (pulando)")
        return 0

    from app.services.gmail_imap import fetch_oab_es_emails

    loop = asyncio.get_event_loop()
    try:
        emails = await loop.run_in_executor(None, fetch_oab_es_emails, True, 50)
    except Exception as e:
        logger.error(f"check_gmail_oab_es: erro ao buscar emails: {e}")
        return 0

    if not emails:
        return 0

    saved = 0
    intimacoes_total = 0
    for email in emails:
        try:
            mid = email.get("message_id") or ""
            subject = email.get("subject") or ""
            body_html = email.get("html") or ""
            body_text = email.get("text") or ""

            # Dedup por message_id
            if mid:
                existing = supabase.table("emails_recebidos").select("id").eq(
                    "message_id", mid
                ).limit(1).execute()
                if existing.data:
                    continue

            # Salva cru
            ins = supabase.table("emails_recebidos").insert({
                "from_addr": (email.get("from") or "")[:255],
                "subject": subject[:500],
                "body_html": body_html,
                "body_text": body_text,
                "received_at_source": email.get("date") or "",
                "message_id": mid[:255],
                "imap_uid": (email.get("uid") or "")[:64],
                "processed": False,
            }).execute()
            saved += 1
            email_db_id = ins.data[0]["id"] if ins.data else None

            # Se nao tem publicacoes, marca processed=true e segue
            if not _has_publications(subject, body_html):
                if email_db_id:
                    supabase.table("emails_recebidos").update({
                        "processed": True,
                        "intimacoes_count": 0,
                    }).eq("id", email_db_id).execute()
                continue

            # Tem publicacoes — processa
            if email_db_id and settings.oab_es_enabled:
                count = await process_email_to_intimacoes(email_db_id, body_html, body_text, subject)
                intimacoes_total += count

        except Exception as e:
            logger.error(f"check_gmail_oab_es: erro ao processar email {email.get('uid')}: {e}", exc_info=True)

    logger.info(f"check_gmail_oab_es: {saved} email(s) salvos, {intimacoes_total} intimacao(oes) criada(s)")
    return saved


async def process_email_to_intimacoes(email_db_id: str, body_html: str, body_text: str, subject: str) -> int:
    """Processa 1 email_recebido em intimacoes. Retorna qtd criadas.

    - Parse com email_parser.parse_oab_es_email
    - Para cada intimacao:
        - Hash dedup (mesma logica que AASP)
        - get_or_create processo
        - INSERT em intimacoes
        - notify_nova_intimacao
        - summarize_intimacao (Groq)
    - Atualiza emails_recebidos com processed=true / parse_error
    """
    from app.services.email_parser import parse_oab_es_email

    try:
        intimacoes_parsed = parse_oab_es_email(body_html, body_text, subject)
    except Exception as e:
        logger.error(f"process_email_to_intimacoes: parser falhou: {e}", exc_info=True)
        supabase.table("emails_recebidos").update({
            "parse_error": str(e)[:500],
        }).eq("id", email_db_id).execute()
        return 0

    if not intimacoes_parsed:
        supabase.table("emails_recebidos").update({
            "processed": True,
            "intimacoes_count": 0,
            "parse_error": "Subject indica >0 publicacoes mas parser nao extraiu nenhuma",
        }).eq("id", email_db_id).execute()
        return 0

    # ── Batch dedup por hash ──
    hashes = []
    for item in intimacoes_parsed:
        h = generate_hash(item.get("conteudo", ""), item.get("data_disponibilizacao", ""))
        hashes.append(h)

    existing_resp = supabase.table("intimacoes").select("hash_conteudo").in_(
        "hash_conteudo", hashes
    ).execute()
    existing_set = {r["hash_conteudo"] for r in (existing_resp.data or [])}

    created = 0
    for item, h in zip(intimacoes_parsed, hashes):
        if h in existing_set:
            continue

        numero = item.get("numero_processo") or ""
        conteudo = item.get("conteudo", "")
        data_disp_str = item.get("data_disponibilizacao", "")

        # ── get_or_create processo ──
        processo_id = None
        if numero:
            try:
                proc_resp = supabase.table("processos").select("id").eq("numero", numero).limit(1).execute()
                if proc_resp.data:
                    processo_id = proc_resp.data[0]["id"]
                else:
                    novo = supabase.table("processos").insert({
                        "numero": numero,
                        "vara": item.get("vara") or None,
                        "comarca": item.get("comarca") or None,
                        "partes": item.get("partes") or {"autor": [], "reu": []},
                        "assunto": (item.get("titulo") or "")[:200] or None,
                    }).execute()
                    if novo.data:
                        processo_id = novo.data[0]["id"]
                        logger.info(f"process_email: criado processo novo {numero}")
            except Exception as e:
                logger.error(f"process_email: erro processo {numero}: {e}")

        # ── INSERT intimacao ──
        try:
            intim_data = {
                "processo_id": processo_id,
                "data_disponibilizacao": data_disp_str or None,
                "data_publicacao": item.get("data_publicacao") or None,
                "conteudo": conteudo,
                "diario_oficial": item.get("diario_oficial") or None,
                "caderno": item.get("caderno") or None,
                "pagina": int(item["pagina"]) if (item.get("pagina") or "").isdigit() else None,
                "hash_conteudo": h,
                "lida": False,
            }
            ins = supabase.table("intimacoes").insert(intim_data).execute()
            if not ins.data:
                continue
            db_intim_id = ins.data[0]["id"]
            created += 1

            # ── Notify Telegram ──
            try:
                data_disp_obj = date.fromisoformat(data_disp_str) if data_disp_str else date.today()
            except Exception:
                data_disp_obj = date.today()

            await notify_nova_intimacao(
                {"processo": numero, "conteudo": conteudo, "diario": item.get("diario_oficial")},
                data_disp_obj,
                db_intim_id,
            )

            # ── AI summary (Groq) ──
            if settings.groq_api_key:
                try:
                    resumo = await summarize_intimacao(conteudo)
                    if resumo:
                        await bot.app.bot.send_message(
                            chat_id=settings.telegram_chat_id,
                            text=f"🤖 <b>Resumo IA:</b>\n{resumo}",
                            parse_mode="HTML",
                        )
                except Exception as e:
                    logger.error(f"process_email: groq summary erro: {e}")

            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"process_email: erro insert intimacao: {e}", exc_info=True)

    # ── Marca email como processado ──
    supabase.table("emails_recebidos").update({
        "processed": True,
        "intimacoes_count": created,
    }).eq("id", email_db_id).execute()

    return created