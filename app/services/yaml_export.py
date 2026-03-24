import yaml
from typing import Optional
from datetime import date
from uuid import UUID


def export_processo_yaml(
    processo: dict,
    intimacoes: list = None,
    tarefas: list = None
) -> str:
    data = {
        "processo": {
            "numero": processo.get("numero"),
            "vara": processo.get("vara"),
            "comarca": processo.get("comarca"),
            "assunto": processo.get("assunto"),
            "sintese": processo.get("sintese"),
            "partes": processo.get("partes", {"autor": [], "reu": []}),
            "valor_causa": float(processo["valor_causa"]) if processo.get("valor_causa") else None,
            "data_distribuicao": processo.get("data_distribuicao")
        }
    }
    
    if intimacoes:
        data["intimacoes"] = [
            {
                "data": i.get("data_disponibilizacao"),
                "conteudo": i.get("conteudo"),
                "diario": i.get("diario_oficial"),
                "lida": i.get("lida")
            }
            for i in intimacoes
        ]
    
    if tarefas:
        data["tarefas_pendentes"] = [
            {
                "titulo": t.get("titulo"),
                "vencimento": t.get("data_vencimento"),
                "tipo": t.get("tipo"),
                "prioridade": t.get("prioridade"),
                "concluida": t.get("concluida")
            }
            for t in tarefas
            if not t.get("concluida")
        ]
    
    return yaml.dump(data, allow_unicode=True, default_flow_style=False)
