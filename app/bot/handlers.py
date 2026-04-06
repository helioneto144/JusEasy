import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from datetime import date, timedelta, datetime
from app.database.supabase_client import (
    supabase,
    get_processos,
    get_processo_by_numero,
    get_processo_by_id,
    get_intimacoes_nao_lidas,
    get_intimacoes_by_processo,
    get_tarefas_pendentes,
    get_tarefas_por_data,
    create_tarefa,
    get_tarefas_by_processo,
    marcar_intimacao_lida,
    concluir_tarefa,
    get_stats,
    get_intimacao_by_id,
    get_tarefas_urgentes,
    archive_processo,
    delete_tarefa,
    create_nota,
    get_notas_by_processo,
)
from app.services.yaml_export import export_processo_yaml
from app.services.ai_service import ask_ai
from app.bot.keyboards import (
    kb_menu_principal,
    kb_intimacao,
    kb_processo,
    kb_tarefa,
    kb_voltar,
)

logger = logging.getLogger(__name__)

PRIORIDADE_EMOJI = {"urgente": "🔴", "alta": "🟠", "media": "🟡", "baixa": "🟢"}
TIPO_EMOJI = {"prazo": "⏰", "audiencia": "🏛️", "peticao": "📄", "recurso": "📂"}


# ─────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────

def fmt_data(data_str: str) -> str:
    """Converte YYYY-MM-DD para DD/MM/YYYY."""
    if not data_str:
        return "?"
    try:
        dt = datetime.fromisoformat(str(data_str)[:10])
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(data_str)[:10]


def safe_md(text: str) -> str:
    """Remove caracteres que quebram Markdown."""
    for ch in ["*", "_", "`", "["]:
        text = text.replace(ch, "")
    return text


# ─────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"[/start] user={update.effective_user.id}")
    text = (
        "⚖️ <b>JusEasy — Gestão de Processos Jurídicos</b>\n\n"
        "Escolha uma opção abaixo ou use os comandos:\n\n"
        "📋 /intimacoes — Intimações não lidas\n"
        "📁 /processos — Listar processos\n"
        "📝 /tarefas — Tarefas pendentes\n"
        "⚠️ /prazos — Prazos agrupados por urgência\n"
        "📅 /hoje — Tarefas de hoje\n"
        "📅 /semana — Tarefas da semana\n"
        "📅 /calendario — Visão semanal\n"
        "➕ /tarefa — Criar nova tarefa\n"
        "📝 /nota — Anotar em processo\n"
        "🔍 /busca — Buscar em tudo\n"
        "📊 /status — Resumo do sistema\n"
        "📊 /stats — Estatísticas detalhadas\n"
        "📋 /resumo — Resumo diário agora\n"
        "🤖 /ia — Consultar IA jurídica\n"
        "📄 /yaml — Exportar processo para IA\n"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb_menu_principal())


# ─────────────────────────────────────────────
# /status
# ─────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"[/status] user={update.effective_user.id}")
    stats = await get_stats()
    text = (
        "📊 <b>Status do JusEasy</b>\n\n"
        f"📁 Processos cadastrados: <b>{stats['processos']}</b>\n"
        f"📋 Intimações não lidas: <b>{stats['intimacoes_nao_lidas']}</b>\n"
        f"📝 Tarefas pendentes: <b>{stats['tarefas_pendentes']}</b>\n"
        f"🔴 Tarefas urgentes: <b>{stats['tarefas_urgentes']}</b>\n"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb_voltar())


# ─────────────────────────────────────────────
# /intimacoes
# ─────────────────────────────────────────────

async def cmd_intimacoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"[/intimacoes] user={update.effective_user.id}")
    intimacoes = await get_intimacoes_nao_lidas(limit=10)

    if not intimacoes:
        await update.message.reply_text(
            "✅ <b>Nenhuma intimação não lida!</b>",
            parse_mode="HTML",
            reply_markup=kb_voltar()
        )
        return

    await update.message.reply_text(
        f"📋 <b>{len(intimacoes)} Intimação(ões) Não Lida(s)</b>\n"
        "Cada item abaixo pode ser marcado como lido:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Marcar Todas como Lidas", callback_data="marcar_todas_lidas")]
        ])
    )

    for i, intim in enumerate(intimacoes, 1):
        intim_id = intim.get("id", "")
        data_disp = fmt_data(intim.get("data_disponibilizacao", ""))
        conteudo = intim.get("conteudo", "")[:250].replace("<", "&lt;").replace(">", "&gt;")
        diario = intim.get("diario_oficial", "") or ""

        # Tenta encontrar o processo vinculado
        processo_numero = None
        if intim.get("processo_id"):
            from app.database.supabase_client import get_processo_by_id
            proc = await get_processo_by_id(intim["processo_id"])
            if proc:
                processo_numero = proc.get("numero")

        text = (
            f"<b>{i}. {data_disp}</b>"
            + (f" — <code>{processo_numero}</code>" if processo_numero else "")
            + f"\n📰 {diario}\n\n"
            + f"{conteudo}…"
        )
        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=kb_intimacao(intim_id, processo_numero)
        )


# ─────────────────────────────────────────────
# /processos
# ─────────────────────────────────────────────

async def cmd_processos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"[/processos] user={update.effective_user.id}")
    processos = await get_processos(limit=20)

    if not processos:
        await update.message.reply_text(
            "📁 Nenhum processo cadastrado.",
            parse_mode="HTML",
            reply_markup=kb_voltar()
        )
        return

    text = f"📁 <b>Processos ({len(processos)})</b>\n\n"
    for p in processos:
        numero = p.get("numero", "")
        assunto = p.get("assunto") or ""
        comarca = p.get("comarca") or ""
        text += f"• <code>{numero}</code>"
        if comarca:
            text += f" — {comarca}"
        if assunto:
            text += f"\n  {assunto[:50]}"
        text += "\n\n"

    text += "Use <code>/processo NUMERO</code> para ver detalhes."
    await update.message.reply_text(text[:4000], parse_mode="HTML", reply_markup=kb_voltar())


# ─────────────────────────────────────────────
# /processo <numero>
# ─────────────────────────────────────────────

async def cmd_processo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "📁 Uso: <code>/processo NUMERO_CNJ</code>\n"
            "Exemplo: <code>/processo 1234567-89.2024.8.26.0002</code>",
            parse_mode="HTML"
        )
        return

    numero = context.args[0]
    logger.info(f"[/processo] numero={numero}")
    processo = await get_processo_by_numero(numero)

    if not processo:
        await update.message.reply_text(
            f"❌ Processo <code>{numero}</code> não encontrado.",
            parse_mode="HTML",
            reply_markup=kb_voltar()
        )
        return

    proc_id = processo.get("id")
    intimacoes = await get_intimacoes_by_processo(proc_id) if proc_id else []
    tarefas = await get_tarefas_by_processo(proc_id) if proc_id else []

    nao_lidas = sum(1 for i in intimacoes if not i.get("lida"))
    pendentes = sum(1 for t in tarefas if not t.get("concluida"))

    text = (
        f"📁 <b>Processo</b> <code>{processo.get('numero')}</code>\n\n"
        f"🏛️ <b>Vara:</b> {processo.get('vara') or 'N/D'}\n"
        f"📍 <b>Comarca:</b> {processo.get('comarca') or 'N/D'}\n"
        f"📄 <b>Assunto:</b> {processo.get('assunto') or 'N/D'}\n"
    )

    if processo.get("data_distribuicao"):
        text += f"📅 <b>Distribuição:</b> {fmt_data(processo['data_distribuicao'])}\n"

    if processo.get("valor_causa"):
        text += f"💰 <b>Valor da Causa:</b> R$ {processo['valor_causa']:,.2f}\n"

    text += f"\n📋 <b>Intimações:</b> {len(intimacoes)} total, {nao_lidas} não lidas\n"
    text += f"📝 <b>Tarefas:</b> {len(tarefas)} total, {pendentes} pendentes\n"

    if processo.get("sintese"):
        text += f"\n🔍 <b>Síntese:</b>\n{processo['sintese'][:300]}\n"

    # Últimas 2 intimações
    if intimacoes:
        text += "\n<b>Última(s) intimação(ões):</b>\n"
        for intim in intimacoes[:2]:
            data_fmt = fmt_data(intim.get("data_disponibilizacao", ""))
            trecho = intim.get("conteudo", "")[:80].replace("<", "&lt;").replace(">", "&gt;")
            lida_icon = "✅" if intim.get("lida") else "🔔"
            text += f"  {lida_icon} {data_fmt}: {trecho}…\n"

    await update.message.reply_text(
        text[:4000],
        parse_mode="HTML",
        reply_markup=kb_processo(numero, proc_id)
    )


# ─────────────────────────────────────────────
# /tarefas
# ─────────────────────────────────────────────

async def cmd_tarefas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"[/tarefas] user={update.effective_user.id}")
    tarefas = await get_tarefas_pendentes(limit=20)

    if not tarefas:
        await update.message.reply_text(
            "✅ <b>Nenhuma tarefa pendente!</b>",
            parse_mode="HTML",
            reply_markup=kb_voltar()
        )
        return

    text = f"📝 <b>Tarefas Pendentes ({len(tarefas)})</b>\n\n"
    for t in tarefas:
        prioridade = t.get("prioridade", "media")
        tipo = t.get("tipo", "prazo")
        emoji_p = PRIORIDADE_EMOJI.get(prioridade, "⚪")
        emoji_t = TIPO_EMOJI.get(tipo, "📌")
        data_fmt = fmt_data(t.get("data_vencimento", ""))
        text += f"{emoji_p} {emoji_t} <b>{t.get('titulo', '')}</b>\n"
        text += f"   📅 {data_fmt}\n\n"

    text += "Use <code>/prazos</code> para ver agrupado por urgência."
    await update.message.reply_text(text[:4000], parse_mode="HTML", reply_markup=kb_voltar())


# ─────────────────────────────────────────────
# /prazos — agrupado por urgência
# ─────────────────────────────────────────────

async def cmd_prazos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"[/prazos] user={update.effective_user.id}")
    tarefas = await get_tarefas_pendentes(limit=50)

    if not tarefas:
        await update.message.reply_text(
            "✅ <b>Nenhum prazo pendente!</b>",
            parse_mode="HTML",
            reply_markup=kb_voltar()
        )
        return

    hoje = date.today()
    amanha = hoje + timedelta(days=1)
    semana = hoje + timedelta(days=7)

    grupos = {
        "🚨 Vencidas / Hoje": [],
        "⚠️ Amanhã": [],
        "📅 Esta Semana": [],
        "📌 Futuro": [],
    }

    for t in tarefas:
        data_str = t.get("data_vencimento")
        if not data_str:
            grupos["📌 Futuro"].append(t)
            continue
        try:
            data_t = date.fromisoformat(str(data_str)[:10])
        except Exception:
            grupos["📌 Futuro"].append(t)
            continue

        if data_t <= hoje:
            grupos["🚨 Vencidas / Hoje"].append(t)
        elif data_t == amanha:
            grupos["⚠️ Amanhã"].append(t)
        elif data_t <= semana:
            grupos["📅 Esta Semana"].append(t)
        else:
            grupos["📌 Futuro"].append(t)

    text = "⚠️ <b>Prazos por Urgência</b>\n\n"
    for grupo, items in grupos.items():
        if not items:
            continue
        text += f"<b>{grupo} ({len(items)})</b>\n"
        for t in items:
            emoji_p = PRIORIDADE_EMOJI.get(t.get("prioridade", "media"), "⚪")
            data_fmt = fmt_data(t.get("data_vencimento", ""))
            tarefa_id = t.get("id", "")
            text += f"  {emoji_p} {data_fmt} — {t.get('titulo', '')}\n"
        text += "\n"

    # Envia cada tarefa urgente com botão de concluir
    await update.message.reply_text(text[:4000], parse_mode="HTML")

    urgentes = grupos["🚨 Vencidas / Hoje"] + grupos["⚠️ Amanhã"]
    for t in urgentes[:5]:
        tarefa_id = t.get("id", "")
        emoji_p = PRIORIDADE_EMOJI.get(t.get("prioridade", "media"), "⚪")
        tipo_emoji = TIPO_EMOJI.get(t.get("tipo", "prazo"), "📌")
        msg = (
            f"{emoji_p} {tipo_emoji} <b>{t.get('titulo')}</b>\n"
            f"📅 Vencimento: {fmt_data(t.get('data_vencimento', ''))}\n"
            f"Tipo: {t.get('tipo', 'prazo')} | Prioridade: {t.get('prioridade', 'media')}"
        )
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb_tarefa(tarefa_id))


# ─────────────────────────────────────────────
# /hoje
# ─────────────────────────────────────────────

async def cmd_hoje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hoje = date.today()
    tarefas = await get_tarefas_por_data(hoje)

    if not tarefas:
        await update.message.reply_text(
            f"📅 <b>{hoje.strftime('%d/%m/%Y')}</b>\n\n✅ Sem tarefas para hoje!",
            parse_mode="HTML",
            reply_markup=kb_voltar()
        )
        return

    text = f"📅 <b>Hoje — {hoje.strftime('%d/%m/%Y')}</b>\n\n"
    for t in tarefas:
        emoji_p = PRIORIDADE_EMOJI.get(t.get("prioridade", "media"), "⚪")
        tipo_emoji = TIPO_EMOJI.get(t.get("tipo", "prazo"), "📌")
        text += f"{emoji_p} {tipo_emoji} {t.get('titulo', '')}\n"

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb_voltar())


# ─────────────────────────────────────────────
# /semana
# ─────────────────────────────────────────────

async def cmd_semana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hoje = date.today()
    fim = hoje + timedelta(days=7)
    tarefas = await get_tarefas_por_data(hoje, fim)

    if not tarefas:
        await update.message.reply_text(
            "✅ <b>Sem tarefas para esta semana!</b>",
            parse_mode="HTML",
            reply_markup=kb_voltar()
        )
        return

    text = f"📅 <b>Próximos 7 dias</b> ({hoje.strftime('%d/%m')} – {fim.strftime('%d/%m')})\n\n"
    for t in tarefas:
        data_fmt = fmt_data(t.get("data_vencimento", ""))
        emoji_p = PRIORIDADE_EMOJI.get(t.get("prioridade", "media"), "⚪")
        tipo_emoji = TIPO_EMOJI.get(t.get("tipo", "prazo"), "📌")
        text += f"{emoji_p} {tipo_emoji} <b>{data_fmt}</b> — {t.get('titulo', '')}\n"

    await update.message.reply_text(text[:4000], parse_mode="HTML", reply_markup=kb_voltar())


# ─────────────────────────────────────────────
# /tarefa TITULO | DATA | TIPO | PRIORIDADE
# ─────────────────────────────────────────────

async def cmd_tarefa_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "➕ <b>Criar Tarefa</b>\n\n"
            "Formato:\n<code>/tarefa TITULO | DATA | TIPO | PRIORIDADE</code>\n\n"
            "Exemplos:\n"
            "<code>/tarefa Responder intimação | 2024-04-10 | prazo | alta</code>\n"
            "<code>/tarefa Audiência instrução | 2024-04-15 | audiencia | urgente</code>\n\n"
            "Tipos: prazo, audiencia, peticao, recurso\n"
            "Prioridades: urgente, alta, media, baixa",
            parse_mode="HTML"
        )
        return

    full_text = " ".join(context.args)
    parts = [p.strip() for p in full_text.split("|")]

    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Formato incorreto.\nUse: <code>/tarefa TITULO | DATA</code>",
            parse_mode="HTML"
        )
        return

    titulo = parts[0]
    try:
        data_venc = date.fromisoformat(parts[1])
    except ValueError:
        await update.message.reply_text(
            "❌ Data inválida. Use formato <code>YYYY-MM-DD</code>",
            parse_mode="HTML"
        )
        return

    tipo = parts[2] if len(parts) > 2 else "prazo"
    prioridade = parts[3] if len(parts) > 3 else "media"

    # Valida enums
    tipos_validos = ["prazo", "audiencia", "peticao", "recurso"]
    prioridades_validas = ["urgente", "alta", "media", "baixa"]
    tipo = tipo if tipo in tipos_validos else "prazo"
    prioridade = prioridade if prioridade in prioridades_validas else "media"

    await create_tarefa(titulo, data_venc, tipo, prioridade)

    emoji_p = PRIORIDADE_EMOJI.get(prioridade, "⚪")
    tipo_emoji = TIPO_EMOJI.get(tipo, "📌")
    await update.message.reply_text(
        f"✅ <b>Tarefa criada!</b>\n\n"
        f"{emoji_p} {tipo_emoji} <b>{titulo}</b>\n"
        f"📅 Vencimento: {data_venc.strftime('%d/%m/%Y')}\n"
        f"Tipo: {tipo} | Prioridade: {prioridade}",
        parse_mode="HTML",
        reply_markup=kb_voltar()
    )


# ─────────────────────────────────────────────
# /yaml <numero>
# ─────────────────────────────────────────────

async def cmd_yaml(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Uso: <code>/yaml NUMERO_PROCESSO</code>",
            parse_mode="HTML"
        )
        return

    numero = context.args[0]
    logger.info(f"[/yaml] numero={numero}")
    processo = await get_processo_by_numero(numero)

    if not processo:
        await update.message.reply_text(
            f"❌ Processo <code>{numero}</code> não encontrado.",
            parse_mode="HTML"
        )
        return

    processo_id = processo.get("id")
    intimacoes = await get_intimacoes_by_processo(processo_id) if processo_id else []
    tarefas = await get_tarefas_by_processo(processo_id) if processo_id else []

    processo_dict = {
        "numero": processo.get("numero"),
        "vara": processo.get("vara"),
        "comarca": processo.get("comarca"),
        "assunto": processo.get("assunto"),
        "sintese": processo.get("sintese"),
        "partes": processo.get("partes"),
        "valor_causa": processo.get("valor_causa"),
        "data_distribuicao": processo.get("data_distribuicao"),
    }

    intimacoes_list = [
        {
            "data_disponibilizacao": i.get("data_disponibilizacao", ""),
            "conteudo": i.get("conteudo", ""),
            "diario_oficial": i.get("diario_oficial", ""),
            "lida": i.get("lida", False),
        }
        for i in intimacoes
    ]
    tarefas_list = [
        {
            "titulo": t.get("titulo", ""),
            "data_vencimento": str(t.get("data_vencimento", "")),
            "tipo": t.get("tipo", ""),
            "prioridade": t.get("prioridade", ""),
            "concluida": t.get("concluida", False),
        }
        for t in tarefas
    ]

    yaml_str = export_processo_yaml(processo_dict, intimacoes_list, tarefas_list)

    # Envia como documento .yaml para facilitar download e colagem em IAs
    import io
    yaml_bytes = yaml_str.encode("utf-8")
    await update.message.reply_document(
        document=io.BytesIO(yaml_bytes),
        filename=f"processo_{numero.replace('/', '_')}.yaml",
        caption=f"📄 YAML exportado — <code>{numero}</code>",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# /ia [numero] <pergunta>
# ─────────────────────────────────────────────

async def cmd_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🤖 <b>Consulta de IA Jurídica</b>\n\n"
            "Modo simples:\n<code>/ia Qual é o prazo para recurso ordinário?</code>\n\n"
            "Com contexto de processo:\n"
            "<code>/ia 1234567-89.2024.8.26.0002 Qual a situação atual?</code>",
            parse_mode="HTML"
        )
        return

    await update.message.reply_text("🤖 Consultando IA…", parse_mode="HTML")

    args = context.args
    context_yaml = ""
    question = " ".join(args)

    # Detecta se o primeiro arg parece um número de processo (contém traços e pontos)
    primeiro = args[0]
    if "-" in primeiro and "." in primeiro and len(primeiro) > 15:
        numero = primeiro
        question = " ".join(args[1:])
        if not question:
            await update.message.reply_text(
                "❌ Após o número do processo, inclua sua pergunta.\n"
                "Exemplo: <code>/ia 1234... Qual a situação?</code>",
                parse_mode="HTML"
            )
            return
        processo = await get_processo_by_numero(numero)
        if processo:
            proc_id = processo.get("id")
            intimacoes = await get_intimacoes_by_processo(proc_id) if proc_id else []
            tarefas = await get_tarefas_by_processo(proc_id) if proc_id else []
            processo_dict = {
                "numero": processo.get("numero"),
                "vara": processo.get("vara"),
                "comarca": processo.get("comarca"),
                "assunto": processo.get("assunto"),
                "sintese": processo.get("sintese"),
                "partes": processo.get("partes"),
            }
            intimacoes_list = [
                {
                    "data": i.get("data_disponibilizacao", ""),
                    "conteudo": i.get("conteudo", "")[:500],
                    "lida": i.get("lida", False),
                }
                for i in intimacoes[:5]
            ]
            tarefas_list = [
                {
                    "titulo": t.get("titulo", ""),
                    "data_vencimento": str(t.get("data_vencimento", "")),
                    "prioridade": t.get("prioridade", ""),
                    "concluida": t.get("concluida", False),
                }
                for t in tarefas
            ]
            context_yaml = export_processo_yaml(processo_dict, intimacoes_list, tarefas_list)
        else:
            await update.message.reply_text(
                f"⚠️ Processo <code>{numero}</code> não encontrado. Respondendo sem contexto…",
                parse_mode="HTML"
            )

    logger.info(f"[/ia] question={question[:80]}")
    answer = await ask_ai(question, context_yaml)

    # Telegram tem limite de 4096 chars por mensagem
    for i in range(0, len(answer), 4000):
        chunk = answer[i:i + 4000]
        await update.message.reply_text(
            f"🤖 <b>JusEasy IA</b>\n\n{chunk}",
            parse_mode="HTML",
            reply_markup=kb_voltar() if i + 4000 >= len(answer) else None,
        )


# ─────────────────────────────────────────────
# CALLBACK QUERY HANDLER (botões inline)
# ─────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    logger.info(f"[callback] data={data}")

    # ── Menu principal ──
    if data.startswith("menu:"):
        action = data.split(":")[1]
        fake_update = update
        fake_update._effective_message = query.message
        if action == "start":
            await query.edit_message_text(
                "⚖️ <b>JusEasy — Menu Principal</b>",
                parse_mode="HTML",
                reply_markup=kb_menu_principal()
            )
        elif action == "intimacoes":
            intimacoes = await get_intimacoes_nao_lidas(limit=5)
            if not intimacoes:
                await query.edit_message_text("✅ Nenhuma intimação não lida.", parse_mode="HTML", reply_markup=kb_voltar())
            else:
                await query.edit_message_text(
                    f"📋 <b>{len(intimacoes)} Intimação(ões) não lida(s)</b>\nUse /intimacoes para ver com botões.",
                    parse_mode="HTML",
                    reply_markup=kb_voltar()
                )
        elif action == "processos":
            processos = await get_processos(limit=10)
            if not processos:
                await query.edit_message_text("📁 Nenhum processo.", parse_mode="HTML", reply_markup=kb_voltar())
            else:
                text = f"📁 <b>{len(processos)} Processo(s)</b>\nUse /processos para ver completo."
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb_voltar())
        elif action == "tarefas":
            tarefas = await get_tarefas_pendentes(limit=5)
            text = f"📝 <b>{len(tarefas)} tarefa(s) pendente(s)</b>\nUse /tarefas para ver com detalhes."
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb_voltar())
        elif action == "hoje":
            hoje = date.today()
            tarefas = await get_tarefas_por_data(hoje)
            if not tarefas:
                text = f"📅 <b>{hoje.strftime('%d/%m/%Y')}</b>\n✅ Sem tarefas hoje!"
            else:
                text = f"📅 <b>Hoje — {hoje.strftime('%d/%m/%Y')}</b>\n\n"
                for t in tarefas:
                    emoji_p = PRIORIDADE_EMOJI.get(t.get("prioridade", "media"), "⚪")
                    text += f"{emoji_p} {t.get('titulo', '')}\n"
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb_voltar())
        elif action == "prazos":
            await query.edit_message_text(
                "⚠️ Use o comando /prazos para ver tarefas com botões de conclusão.",
                parse_mode="HTML",
                reply_markup=kb_voltar()
            )
        elif action == "status":
            stats = await get_stats()
            text = (
                "📊 <b>Status do JusEasy</b>\n\n"
                f"📁 Processos: <b>{stats['processos']}</b>\n"
                f"📋 Intimações não lidas: <b>{stats['intimacoes_nao_lidas']}</b>\n"
                f"📝 Tarefas pendentes: <b>{stats['tarefas_pendentes']}</b>\n"
                f"🔴 Urgentes: <b>{stats['tarefas_urgentes']}</b>\n"
            )
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb_voltar())

    # ── Marcar intimação como lida ──
    elif data.startswith("marcar_lida:"):
        intim_id = data.split(":")[1]
        await marcar_intimacao_lida(intim_id)
        await query.edit_message_text(
            query.message.text + "\n\n✅ <i>Marcada como lida.</i>",
            parse_mode="HTML"
        )

    # ── Concluir tarefa ──
    elif data.startswith("concluir_tarefa:"):
        tarefa_id = data.split(":")[1]
        await concluir_tarefa(tarefa_id)
        await query.edit_message_text(
            query.message.text + "\n\n✅ <i>Tarefa concluída!</i>",
            parse_mode="HTML"
        )

    # ── Ver processo ──
    elif data.startswith("ver_processo:"):
        numero = data.split(":")[1]
        processo = await get_processo_by_numero(numero)
        if not processo:
            await query.answer("Processo não encontrado.", show_alert=True)
            return
        proc_id = processo.get("id")
        intimacoes = await get_intimacoes_by_processo(proc_id) if proc_id else []
        tarefas = await get_tarefas_by_processo(proc_id) if proc_id else []
        nao_lidas = sum(1 for i in intimacoes if not i.get("lida"))
        pendentes = sum(1 for t in tarefas if not t.get("concluida"))
        text = (
            f"📁 <b>Processo</b> <code>{processo.get('numero')}</code>\n\n"
            f"🏛️ Vara: {processo.get('vara') or 'N/D'}\n"
            f"📍 Comarca: {processo.get('comarca') or 'N/D'}\n"
            f"📄 Assunto: {(processo.get('assunto') or 'N/D')[:80]}\n\n"
            f"📋 {len(intimacoes)} intimações ({nao_lidas} não lidas)\n"
            f"📝 {len(tarefas)} tarefas ({pendentes} pendentes)\n"
        )
        await query.edit_message_text(
            text, parse_mode="HTML",
            reply_markup=kb_processo(numero, proc_id)
        )

    # ── Intimações de um processo ──
    elif data.startswith("intims_processo:"):
        proc_id = data.split(":")[1]
        intimacoes = await get_intimacoes_by_processo(proc_id)
        if not intimacoes:
            await query.answer("Nenhuma intimação para este processo.", show_alert=True)
            return
        text = f"📋 <b>Intimações ({len(intimacoes)})</b>\n\n"
        for intim in intimacoes[:5]:
            lida = "✅" if intim.get("lida") else "🔔"
            data_fmt = fmt_data(intim.get("data_disponibilizacao", ""))
            trecho = intim.get("conteudo", "")[:100].replace("<", "&lt;")
            text += f"{lida} {data_fmt}\n{trecho}…\n\n"
        await query.edit_message_text(text[:4000], parse_mode="HTML", reply_markup=kb_voltar())

    # ── Tarefas de um processo ──
    elif data.startswith("tarefas_processo:"):
        proc_id = data.split(":")[1]
        tarefas = await get_tarefas_by_processo(proc_id)
        if not tarefas:
            await query.answer("Nenhuma tarefa para este processo.", show_alert=True)
            return
        text = f"📝 <b>Tarefas ({len(tarefas)})</b>\n\n"
        for t in tarefas:
            status = "✅" if t.get("concluida") else "🔲"
            emoji_p = PRIORIDADE_EMOJI.get(t.get("prioridade", "media"), "⚪")
            data_fmt = fmt_data(t.get("data_vencimento", ""))
            text += f"{status} {emoji_p} {t.get('titulo', '')} — {data_fmt}\n"
        await query.edit_message_text(text[:4000], parse_mode="HTML", reply_markup=kb_voltar())

    # ── Analisar com IA ──
    elif data.startswith("analisar_ia:"):
        numero = data.split(":")[1]
        await query.edit_message_text(
            f"🤖 <b>Análise IA</b>\n\nUse o comando:\n<code>/ia {numero} Sua pergunta aqui</code>",
            parse_mode="HTML",
            reply_markup=kb_voltar()
        )

    # ── Arquivar processo ──
    elif data.startswith("arquivar_processo:"):
        proc_id = data.split(":")[1]
        await archive_processo(proc_id)
        await query.edit_message_text(
            query.message.text + "\n\n📦 <i>Processo arquivado.</i>",
            parse_mode="HTML"
        )

    # ── Deletar tarefa ──
    elif data.startswith("deletar_tarefa:"):
        tarefa_id = data.split(":")[1]
        await delete_tarefa(tarefa_id)
        await query.edit_message_text(
            "🗑️ <i>Tarefa deletada.</i>",
            parse_mode="HTML"
        )

    # ── Marcar todas intimações como lidas ──
    elif data == "marcar_todas_lidas":
        nao_lidas = await get_intimacoes_nao_lidas(limit=100)
        count = 0
        for intim in nao_lidas:
            await marcar_intimacao_lida(intim["id"])
            count += 1
        await query.edit_message_text(
            f"✅ <b>{count} intimação(ões) marcada(s) como lida(s).</b>",
            parse_mode="HTML",
            reply_markup=kb_voltar()
        )


# ─────────────────────────────────────────────
# /resumo — disparo manual do resumo diário
# ─────────────────────────────────────────────

async def cmd_resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"[/resumo] user={update.effective_user.id}")
    from app.scheduler.jobs import resumo_diario
    await update.message.reply_text("⏳ Gerando resumo…", parse_mode="HTML")
    await resumo_diario(force=True)


# ─────────────────────────────────────────────
# /calendario — visão semanal
# ─────────────────────────────────────────────

async def cmd_calendario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"[/calendario] user={update.effective_user.id}")
    hoje = date.today()
    dias_semana = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
    inicio = hoje
    fim = hoje + timedelta(days=6)

    tarefas = await get_tarefas_por_data(inicio, fim)
    intimacoes_raw = supabase.table("intimacoes").select("*").gte(
        "data_disponibilizacao", str(inicio)
    ).lte("data_disponibilizacao", str(fim)).execute()
    intimacoes = intimacoes_raw.data or []

    text = f"📅 <b>Semana {inicio.strftime('%d/%m')} — {fim.strftime('%d/%m')}</b>\n\n"

    for i in range(7):
        dia = inicio + timedelta(days=i)
        dia_str = str(dia)
        dia_nome = dias_semana[dia.weekday()]
        dia_fmt = dia.strftime("%d")
        marcador = " 👈" if dia == hoje else ""

        tarefas_dia = [t for t in tarefas if str(t.get("data_vencimento", ""))[:10] == dia_str]
        intims_dia = [i for i in intimacoes if str(i.get("data_disponibilizacao", ""))[:10] == dia_str]

        if not tarefas_dia and not intims_dia:
            text += f"<b>{dia_nome} {dia_fmt}</b>{marcador} ───\n  <i>(vazio)</i>\n\n"
        else:
            text += f"<b>{dia_nome} {dia_fmt}</b>{marcador} ───\n"
            for t in tarefas_dia:
                emoji_p = PRIORIDADE_EMOJI.get(t.get("prioridade", "media"), "⚪")
                text += f"  {emoji_p} {t.get('titulo', '')}\n"
            for intim in intims_dia:
                text += f"  📋 Intimação: {(intim.get('conteudo') or '')[:60]}…\n"
            text += "\n"

    await update.message.reply_text(text[:4000], parse_mode="HTML", reply_markup=kb_voltar())


# ─────────────────────────────────────────────
# /nota <numero> <texto>
# ─────────────────────────────────────────────

async def cmd_nota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📝 <b>Adicionar Nota a Processo</b>\n\n"
            "Uso: <code>/nota NUMERO_PROCESSO Texto da anotação</code>\n\n"
            "Exemplo:\n<code>/nota 1234567-89.2024.8.26.0002 Cliente ligou pedindo atualização</code>",
            parse_mode="HTML"
        )
        return

    numero = context.args[0]
    texto = " ".join(context.args[1:])
    processo = await get_processo_by_numero(numero)

    if not processo:
        await update.message.reply_text(
            f"❌ Processo <code>{numero}</code> não encontrado.",
            parse_mode="HTML"
        )
        return

    proc_id = processo.get("id")
    await create_nota(proc_id, texto)

    await update.message.reply_text(
        f"📝 <b>Nota adicionada!</b>\n\n"
        f"Processo: <code>{numero}</code>\n"
        f"Nota: {texto[:200]}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📁 Ver Processo", callback_data=f"ver_processo:{numero}")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="menu:start")]
        ])
    )


# ─────────────────────────────────────────────
# /busca <termo>
# ─────────────────────────────────────────────

async def cmd_busca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>Busca Global</b>\n\nUso: <code>/busca TERMO</code>\n"
            "Busca em processos, intimações e tarefas.",
            parse_mode="HTML"
        )
        return

    termo = " ".join(context.args)
    q_safe = termo.replace("%", "").replace("'", "").replace(";", "")
    logger.info(f"[/busca] termo={q_safe[:50]}")

    procs = supabase.table("processos").select("numero,assunto,comarca").or_(
        f"numero.ilike.%{q_safe}%,assunto.ilike.%{q_safe}%,comarca.ilike.%{q_safe}%"
    ).limit(5).execute()
    intims = supabase.table("intimacoes").select("id,conteudo,data_disponibilizacao").ilike(
        "conteudo", f"%{q_safe}%"
    ).limit(5).execute()
    tars = supabase.table("tarefas").select("id,titulo,data_vencimento,prioridade").ilike(
        "titulo", f"%{q_safe}%"
    ).limit(5).execute()

    text = f"🔍 <b>Resultados para \"{termo}\"</b>\n\n"
    found = False

    if procs.data:
        found = True
        text += "<b>📁 Processos:</b>\n"
        for p in procs.data:
            text += f"  • <code>{p.get('numero', '')}</code> — {(p.get('assunto') or p.get('comarca') or '')[:40]}\n"
        text += "\n"

    if intims.data:
        found = True
        text += "<b>📋 Intimações:</b>\n"
        for i in intims.data:
            text += f"  • {fmt_data(i.get('data_disponibilizacao', ''))} — {(i.get('conteudo') or '')[:60]}…\n"
        text += "\n"

    if tars.data:
        found = True
        text += "<b>📝 Tarefas:</b>\n"
        for t in tars.data:
            emoji = PRIORIDADE_EMOJI.get(t.get("prioridade", "media"), "⚪")
            text += f"  {emoji} {t.get('titulo', '')} — {fmt_data(t.get('data_vencimento', ''))}\n"
        text += "\n"

    if not found:
        text += "Nenhum resultado encontrado."

    await update.message.reply_text(text[:4000], parse_mode="HTML", reply_markup=kb_voltar())


# ─────────────────────────────────────────────
# /stats — estatísticas detalhadas
# ─────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"[/stats] user={update.effective_user.id}")
    stats = await get_stats()

    # Processos arquivados
    arq = supabase.table("processos").select("id", count="exact").eq("arquivado", True).execute()
    arq_count = arq.count or 0

    # Total intimações
    total_intim = supabase.table("intimacoes").select("id", count="exact").execute()
    total_intim_count = total_intim.count or 0

    # Tarefas concluídas esta semana
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    concluidas = supabase.table("tarefas").select("id", count="exact").eq(
        "concluida", True
    ).gte("data_vencimento", str(inicio_semana)).execute()
    concluidas_count = concluidas.count or 0

    # Próximo prazo
    prox = supabase.table("tarefas").select("titulo,data_vencimento").eq(
        "concluida", False
    ).gte("data_vencimento", str(hoje)).order("data_vencimento").limit(1).execute()
    prox_prazo = prox.data[0] if prox.data else None

    text = (
        "📊 <b>Estatísticas JusEasy</b>\n\n"
        f"📁 Processos: <b>{stats['processos']}</b> ativos / <b>{arq_count}</b> arquivados\n"
        f"📋 Intimações: <b>{stats['intimacoes_nao_lidas']}</b> não lidas / <b>{total_intim_count}</b> total\n"
        f"📝 Tarefas: <b>{stats['tarefas_pendentes']}</b> pendentes / <b>{stats['tarefas_urgentes']}</b> urgentes\n"
        f"✅ Concluídas esta semana: <b>{concluidas_count}</b>\n"
    )

    if prox_prazo:
        dias_rest = (date.fromisoformat(str(prox_prazo["data_vencimento"])[:10]) - hoje).days
        text += f"\n⚠️ Próximo prazo: <b>{prox_prazo['titulo']}</b> ({dias_rest} dia{'s' if dias_rest != 1 else ''})"

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb_voltar())


# ─────────────────────────────────────────────
# REGISTRO DE HANDLERS
# ─────────────────────────────────────────────

def setup_handlers(app):
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("resumo", cmd_resumo))
    app.add_handler(CommandHandler("intimacoes", cmd_intimacoes))
    app.add_handler(CommandHandler("processos", cmd_processos))
    app.add_handler(CommandHandler("processo", cmd_processo))
    app.add_handler(CommandHandler("tarefas", cmd_tarefas))
    app.add_handler(CommandHandler("prazos", cmd_prazos))
    app.add_handler(CommandHandler("hoje", cmd_hoje))
    app.add_handler(CommandHandler("semana", cmd_semana))
    app.add_handler(CommandHandler("tarefa", cmd_tarefa_create))
    app.add_handler(CommandHandler("yaml", cmd_yaml))
    app.add_handler(CommandHandler("ia", cmd_ia))
    app.add_handler(CommandHandler("calendario", cmd_calendario))
    app.add_handler(CommandHandler("nota", cmd_nota))
    app.add_handler(CommandHandler("busca", cmd_busca))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CallbackQueryHandler(callback_handler))