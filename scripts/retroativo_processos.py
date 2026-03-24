from app.database.supabase_client import supabase
from app.services.aasp import parse_dados_processo

processos = supabase.table("processos").select("*").execute().data
print(f"Total de processos: {len(processos)}")

atualizados = 0
for proc in processos:
    proc_id = proc["id"]
    numero = proc["numero"]
    
    intimacoes = supabase.table("intimacoes").select("conteudo").eq("processo_id", proc_id).execute().data
    
    if not intimacoes:
        print(f"Sem intimações: {numero}")
        continue
    
    conteudo = intimacoes[0]["conteudo"]
    dados = parse_dados_processo(conteudo)
    
    update_data = {}
    if dados["vara"] and not proc.get("vara"):
        update_data["vara"] = dados["vara"]
    if dados["comarca"] and not proc.get("comarca"):
        update_data["comarca"] = dados["comarca"]
    
    partes = proc.get("partes") or {}
    if dados["partes"]["autor"] and not partes.get("autor"):
        update_data["partes"] = {**partes, "autor": dados["partes"]["autor"]}
    if dados["partes"]["reu"] and not partes.get("reu"):
        if "partes" not in update_data:
            update_data["partes"] = {**partes, "reu": dados["partes"]["reu"]}
        else:
            update_data["partes"]["reu"] = dados["partes"]["reu"]
    
    if update_data:
        supabase.table("processos").update(update_data).eq("id", proc_id).execute()
        vara = dados.get("vara")
        comarca = dados.get("comarca")
        n_autores = len(dados["partes"]["autor"])
        n_reus = len(dados["partes"]["reu"])
        print(f"Atualizado {numero}: vara={vara}, comarca={comarca}, autores={n_autores}, reus={n_reus}")
        atualizados += 1
    else:
        print(f"Sem dados novos: {numero}")

print(f"\nTotal atualizados: {atualizados}")
