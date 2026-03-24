import asyncio
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from datetime import date, timedelta
from uuid import UUID

from app.database.supabase_client import (
    supabase,
    get_processos,
    get_processo_by_id,
    update_processo,
    get_intimacoes_nao_lidas,
    get_intimacoes_by_processo,
    get_tarefas_pendentes,
    get_tarefas_by_processo,
    create_tarefa
)
from app.services.yaml_export import export_processo_yaml

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    hoje = date.today()
    loop = asyncio.get_event_loop()

    proc_r, intim_r, tar_r, ultimas_r = await asyncio.gather(
        loop.run_in_executor(None, lambda: supabase.table("processos").select("id", count="exact").eq("arquivado", False).execute()),
        loop.run_in_executor(None, lambda: supabase.table("intimacoes").select("id", count="exact").eq("lida", False).execute()),
        loop.run_in_executor(None, lambda: supabase.table("tarefas").select("id", count="exact").eq("concluida", False).gte("data_vencimento", str(hoje)).execute()),
        loop.run_in_executor(None, lambda: supabase.table("intimacoes").select("*").order("data_disponibilizacao", desc=True).limit(5).execute()),
    )

    return request.app.state.templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "processos_count": proc_r.count or 0,
            "intimacoes_nao_lidas": intim_r.count or 0,
            "tarefas_pendentes": tar_r.count or 0,
            "ultimas_intimacoes": ultimas_r.data,
        }
    )


@router.get("/processos", response_class=HTMLResponse)
async def list_processos(request: Request, q: str = ""):
    query = supabase.table("processos").select("*").order("updated_at", desc=True)
    
    if q:
        q_safe = q.replace("%", "").replace("'", "").replace(";", "").replace(",", "")
        query = query.or_(f"numero.ilike.%{q_safe}%,assunto.ilike.%{q_safe}%,comarca.ilike.%{q_safe}%")
    
    response = query.execute()
    processos = response.data
    
    if request.headers.get("HX-Request"):
        return request.app.state.templates.TemplateResponse(
            "processos/_list.html",
            {"request": request, "processos": processos, "q": q}
        )
    
    return request.app.state.templates.TemplateResponse(
        "processos/list.html",
        {"request": request, "processos": processos, "q": q}
    )


@router.get("/processo/novo", response_class=HTMLResponse)
async def novo_processo_form(request: Request):
    return request.app.state.templates.TemplateResponse(
        "processos/form.html",
        {"request": request, "processo": None}
    )


@router.post("/processo/novo", response_class=HTMLResponse)
async def criar_processo(
    request: Request,
    numero: str = Form(...),
    vara: str = Form(""),
    comarca: str = Form(""),
    assunto: str = Form(""),
    sintese: str = Form(""),
    partes_autor: str = Form(""),
    partes_reu: str = Form(""),
):
    data = {
        "numero": numero,
        "vara": vara or None,
        "comarca": comarca or None,
        "assunto": assunto or None,
        "sintese": sintese or None,
        "partes": {"autor": partes_autor.split("\n") if partes_autor else [], "reu": partes_reu.split("\n") if partes_reu else []}
    }
    
    response = supabase.table("processos").insert(data).execute()
    processo = response.data[0] if response.data else None
    
    if processo:
        return RedirectResponse(url=f"/processo/{processo['id']}", status_code=303)
    
    return RedirectResponse(url="/processos", status_code=303)


@router.get("/processo/{id}", response_class=HTMLResponse)
async def detail_processo(request: Request, id: str):
    processo = await get_processo_by_id(id)
    
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    intimacoes = await get_intimacoes_by_processo(id)
    tarefas = await get_tarefas_by_processo(id)
    
    return request.app.state.templates.TemplateResponse(
        "processos/detail.html",
        {
            "request": request,
            "processo": processo,
            "intimacoes": intimacoes,
            "tarefas": tarefas,
        }
    )


@router.put("/processo/{id}/sintese")
async def update_sintese(id: str, request: Request):
    form_data = await request.form()
    sintese = form_data.get("sintese", "")
    
    supabase.table("processos").update({"sintese": sintese}).eq("id", id).execute()
    
    return JSONResponse({"status": "ok"})


@router.put("/processo/{id}/assunto")
async def update_assunto(id: str, request: Request):
    form_data = await request.form()
    assunto = form_data.get("assunto", "")
    
    supabase.table("processos").update({"assunto": assunto}).eq("id", id).execute()
    
    return JSONResponse({"status": "ok"})


@router.get("/processo/{id}/yaml", response_class=HTMLResponse)
async def export_yaml(request: Request, id: str):
    processo = await get_processo_by_id(id)
    
    if not processo:
        raise HTTPException(status_code=404)
    
    intimacoes = await get_intimacoes_by_processo(id)
    tarefas_pendentes = [t for t in await get_tarefas_by_processo(id) if not t.get("concluida")]
    
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
            "data": i.get("data_disponibilizacao"),
            "conteudo": i.get("conteudo"),
            "diario": i.get("diario_oficial"),
            "lida": i.get("lida")
        }
        for i in intimacoes[:10]
    ]
    
    tarefas_list = [
        {
            "titulo": t.get("titulo"),
            "vencimento": t.get("data_vencimento"),
            "tipo": t.get("tipo"),
            "prioridade": t.get("prioridade"),
            "concluida": t.get("concluida")
        }
        for t in tarefas_pendentes
    ]
    
    yaml_str = export_processo_yaml(processo_dict, intimacoes_list, tarefas_list)
    
    return request.app.state.templates.TemplateResponse(
        "processos/yaml_modal.html",
        {"request": request, "processo": processo, "yaml_content": yaml_str}
    )


@router.get("/intimacoes", response_class=HTMLResponse)
async def list_intimacoes(request: Request, lida: str = ""):
    query = supabase.table("intimacoes").select("*").order("data_disponibilizacao", desc=True)
    
    if lida == "nao":
        query = query.eq("lida", False)
    elif lida == "sim":
        query = query.eq("lida", True)
    
    response = query.limit(50).execute()
    intimacoes = response.data
    
    return request.app.state.templates.TemplateResponse(
        "intimacoes/list.html",
        {"request": request, "intimacoes": intimacoes, "filtro_lida": lida}
    )


@router.post("/intimacao/{id}/ler")
async def marcar_lida(request: Request, id: str):
    supabase.table("intimacoes").update({"lida": True}).eq("id", id).execute()
    
    response = supabase.table("intimacoes").select("*").eq("id", id).single().execute()
    intimacao = response.data
    
    return request.app.state.templates.TemplateResponse(
        "intimacoes/_card.html",
        {"request": request, "intimacao": intimacao}
    )


@router.get("/tarefas", response_class=HTMLResponse)
async def list_tarefas(request: Request):
    response = supabase.table("tarefas").select("*").order("data_vencimento").execute()
    tarefas = response.data
    
    return request.app.state.templates.TemplateResponse(
        "tarefas/list.html",
        {"request": request, "tarefas": tarefas}
    )


@router.post("/tarefa/nova")
async def criar_tarefa_web(request: Request):
    form_data = await request.form()
    
    titulo = form_data.get("titulo", "")
    data_vencimento = form_data.get("data_vencimento", "")
    processo_id = form_data.get("processo_id", "")
    tipo = form_data.get("tipo", "")
    descricao = form_data.get("descricao", "")
    prioridade = form_data.get("prioridade", "media")
    
    data = {
        "titulo": titulo,
        "data_vencimento": data_vencimento,
        "tipo": tipo or None,
        "descricao": descricao or None,
        "prioridade": prioridade,
    }
    if processo_id:
        data["processo_id"] = processo_id
    
    response = supabase.table("tarefas").insert(data).execute()
    tarefa = response.data[0] if response.data else None
    
    return JSONResponse({"status": "ok", "id": tarefa["id"] if tarefa else None})


@router.post("/tarefa/{id}/concluir")
async def concluir_tarefa(id: str):
    supabase.table("tarefas").update({"concluida": True}).eq("id", id).execute()
    return JSONResponse({"status": "ok"})


@router.post("/processo/{id}/arquivar")
async def arquivar_processo(id: str):
    supabase.table("processos").update({"arquivado": True}).eq("id", id).execute()
    return RedirectResponse(url="/processos", status_code=303)


@router.delete("/tarefa/{id}")
async def deletar_tarefa_web(id: str):
    supabase.table("tarefas").delete().eq("id", id).execute()
    return JSONResponse({"status": "ok"})


@router.post("/sync-intimacoes")
async def sync_intimacoes():
    from app.scheduler.jobs import check_intimacoes_periodo
    count = await check_intimacoes_periodo(dias=10)
    return JSONResponse({"status": "ok", "intimacoes_importadas": count})