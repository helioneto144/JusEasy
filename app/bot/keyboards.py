from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def kb_menu_principal() -> InlineKeyboardMarkup:
    """Menu principal com atalhos rápidos."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Intimações", callback_data="menu:intimacoes"),
            InlineKeyboardButton("📁 Processos", callback_data="menu:processos"),
        ],
        [
            InlineKeyboardButton("📝 Tarefas", callback_data="menu:tarefas"),
            InlineKeyboardButton("📅 Hoje", callback_data="menu:hoje"),
        ],
        [
            InlineKeyboardButton("⚠️ Prazos", callback_data="menu:prazos"),
            InlineKeyboardButton("📊 Status", callback_data="menu:status"),
        ],
    ])


def kb_intimacao(intimacao_id: str, processo_numero: str = None) -> InlineKeyboardMarkup:
    """Botões para uma intimação: marcar lida + ver processo."""
    buttons = [
        InlineKeyboardButton("✅ Marcar Lida", callback_data=f"marcar_lida:{intimacao_id}"),
    ]
    row2 = []
    if processo_numero:
        row2.append(
            InlineKeyboardButton("📁 Ver Processo", callback_data=f"ver_processo:{processo_numero}")
        )
    if row2:
        return InlineKeyboardMarkup([[*buttons], row2])
    return InlineKeyboardMarkup([buttons])


def kb_processo(processo_numero: str, processo_id: str = None) -> InlineKeyboardMarkup:
    """Botões para um processo: intimações, tarefas, análise IA e arquivar."""
    pid = processo_id or processo_numero
    buttons = [
        [
            InlineKeyboardButton("📋 Intimações", callback_data=f"intims_processo:{pid}"),
            InlineKeyboardButton("📝 Tarefas", callback_data=f"tarefas_processo:{pid}"),
        ],
        [
            InlineKeyboardButton("🤖 Analisar com IA", callback_data=f"analisar_ia:{processo_numero}"),
            InlineKeyboardButton("📦 Arquivar", callback_data=f"arquivar_processo:{pid}"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def kb_tarefa(tarefa_id: str) -> InlineKeyboardMarkup:
    """Botões para concluir ou deletar tarefa."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Concluir", callback_data=f"concluir_tarefa:{tarefa_id}"),
            InlineKeyboardButton("🗑️ Deletar", callback_data=f"deletar_tarefa:{tarefa_id}"),
        ]
    ])


def kb_voltar() -> InlineKeyboardMarkup:
    """Botão voltar ao menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Menu Principal", callback_data="menu:start")]
    ])
