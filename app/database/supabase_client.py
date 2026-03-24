from supabase import create_client, Client
from app.config import get_settings

settings = get_settings()

supabase: Client = create_client(
    settings.supabase_url,
    settings.supabase_anon_key
)


async def get_processos(limit: int = 20):
    response = supabase.table("processos").select("*").eq("arquivado", False).order("updated_at", desc=True).limit(limit).execute()
    return response.data


async def get_processo_by_numero(numero: str):
    response = supabase.table("processos").select("*").eq("numero", numero).execute()
    return response.data[0] if response.data else None


async def get_processo_by_id(id: str):
    response = supabase.table("processos").select("*").eq("id", id).execute()
    return response.data[0] if response.data else None


async def update_processo(id: str, data: dict):
    response = supabase.table("processos").update(data).eq("id", id).execute()
    return response.data


async def get_intimacoes_nao_lidas(limit: int = 10):
    response = supabase.table("intimacoes").select("*").eq("lida", False).order("data_disponibilizacao", desc=True).limit(limit).execute()
    return response.data


async def get_intimacoes_by_processo(processo_id: str):
    response = supabase.table("intimacoes").select("*").eq("processo_id", processo_id).order("data_disponibilizacao", desc=True).execute()
    return response.data


async def get_tarefas_pendentes(limit: int = 20):
    response = supabase.table("tarefas").select("*").eq("concluida", False).order("data_vencimento").limit(limit).execute()
    return response.data


async def get_tarefas_por_data(data_inicio, data_fim=None):
    query = supabase.table("tarefas").select("*").eq("concluida", False).gte("data_vencimento", str(data_inicio))
    if data_fim:
        query = query.lte("data_vencimento", str(data_fim))
    else:
        query = query.eq("data_vencimento", str(data_inicio))
    response = query.order("data_vencimento").execute()
    return response.data


async def create_tarefa(titulo: str, data_vencimento, tipo: str = "prazo", prioridade: str = "media", processo_id: str = None):
    data = {
        "titulo": titulo,
        "data_vencimento": str(data_vencimento),
        "tipo": tipo,
        "prioridade": prioridade
    }
    if processo_id:
        data["processo_id"] = processo_id
    response = supabase.table("tarefas").insert(data).execute()
    return response.data


async def get_tarefas_by_processo(processo_id: str):
    response = supabase.table("tarefas").select("*").eq("processo_id", processo_id).order("data_vencimento").execute()
    return response.data


async def marcar_intimacao_lida(intimacao_id: str):
    response = supabase.table("intimacoes").update({"lida": True}).eq("id", intimacao_id).execute()
    return response.data


async def concluir_tarefa(tarefa_id: str):
    response = supabase.table("tarefas").update({"concluida": True}).eq("id", tarefa_id).execute()
    return response.data


async def get_intimacao_by_id(intimacao_id: str):
    response = supabase.table("intimacoes").select("*").eq("id", intimacao_id).execute()
    return response.data[0] if response.data else None


async def archive_processo(id: str):
    supabase.table("processos").update({"arquivado": True}).eq("id", id).execute()


async def delete_tarefa(tarefa_id: str):
    supabase.table("tarefas").delete().eq("id", tarefa_id).execute()


async def get_tarefas_urgentes():
    from datetime import date, timedelta
    hoje = date.today()
    amanha = hoje + timedelta(days=1)
    response = supabase.table("tarefas").select("*").eq("concluida", False).lte("data_vencimento", str(amanha)).execute()
    return response.data


async def get_stats():
    # Isso é devagar se o banco for gigante, mas serve pro Oracle v1
    proc = supabase.table("processos").select("id", count="exact").execute()
    intims = supabase.table("intimacoes").select("id", count="exact").eq("lida", False).execute()
    tars = supabase.table("tarefas").select("id", count="exact").eq("concluida", False).execute()

    from datetime import date, timedelta
    amanha = date.today() + timedelta(days=1)
    urg = supabase.table("tarefas").select("id", count="exact").eq("concluida", False).lte("data_vencimento", str(amanha)).execute()

    return {
        "processos": proc.count if proc else 0,
        "intimacoes_nao_lidas": intims.count if intims else 0,
        "tarefas_pendentes": tars.count if tars else 0,
        "tarefas_urgentes": urg.count if urg else 0
    }