import httpx
import re
from typing import Optional, List
from datetime import date, timedelta
from app.config import get_settings

settings = get_settings()


def parse_dados_processo(texto: str) -> dict:
    """
    Extrai vara, comarca e partes do texto da intimação AASP.
    
    Exemplo de texto:
    "Órgão: Vila Velha - Comarca da Capital - 1º Juizado Especial Cível"
    "AUTOR: HELIO LEITE DE MENEZES NETO"
    "REU: INFINYSHOP COMERCIO LTDA, SHPS TECNOLOGIA E SERVICOS LTDA."
    """
    resultado = {
        "vara": None,
        "comarca": None,
        "partes": {"autor": [], "reu": []}
    }
    
    if not texto:
        return resultado
    
    partes_orgao = []
    
    orgao_match = re.search(r'Órgão:\s*(.+?)(?:\n|\r|Data)', texto)
    if orgao_match:
        orgao = orgao_match.group(1).strip()
        partes_orgao = [p.strip() for p in orgao.split(' - ') if p.strip()]
        for parte in partes_orgao:
            parte_lower = parte.lower()
            if 'comarca' in parte_lower:
                resultado["comarca"] = re.sub(r'(?i)comarca\s*(da\s*)?', '', parte).strip()
            elif any(x in parte_lower for x in ['juizado', 'vara', 'cível', 'civil', 'criminal', 'federal', 'trabalho', 'família', 'familia']):
                resultado["vara"] = parte.strip()
    
    if not resultado["comarca"] and partes_orgao:
        for parte in partes_orgao:
            parte_lower = parte.lower()
            if 'foro de' in parte_lower:
                resultado["comarca"] = re.sub(r'(?i)foro\s*(de\s*)?', '', parte).strip()
            elif 'vara' not in parte_lower and 'juizado' not in parte_lower:
                resultado["comarca"] = parte
                break
    
    if not resultado["comarca"] and partes_orgao:
        resultado["comarca"] = partes_orgao[0]
    
    autor_match = re.search(r'(?:AUTOR|REQUERENTE|IMPETRANTE|EXEQUENTE):\s*(.+?)(?:\s+(?:REQUERIDO|R[EÉ]U|EXECUTADO|IMPETRADO):|$)', texto, re.IGNORECASE)
    if autor_match:
        autores = autor_match.group(1).strip()
        resultado["partes"]["autor"] = [a.strip() for a in re.split(r'[,;]\s*(?=[A-Z])', autores) if a.strip()]
    
    reu_match = re.search(r'(?:R[EÉ]U|REQUERIDO|IMPETRADO|EXECUTADO):\s*(.+?)(?:\s+(?:AUTOR|REQUERENTE|EXEQUENTE|IMPETRANTE|Advogado):|$)', texto, re.IGNORECASE)
    if reu_match:
        reus = reu_match.group(1).strip()
        reus = re.sub(r'\s+Advogado.*$', '', reus, flags=re.IGNORECASE)
        resultado["partes"]["reu"] = [r.strip() for r in re.split(r'[,;]\s*(?=[A-Z])', reus) if r.strip()]
    
    if not resultado["partes"]["autor"] and not resultado["partes"]["reu"]:
        partes_match = re.search(r'Parte\(s\):\s*(.+?)(?:\n|\r)', texto, re.IGNORECASE)
        if partes_match:
            partes_texto = partes_match.group(1).strip()
            todas_partes = re.split(r'\s{2,}', partes_texto)
            todas_partes = [p.strip() for p in todas_partes if p.strip() and len(p.strip()) > 3]
            if len(todas_partes) > 1:
                resultado["partes"]["autor"] = [todas_partes[0]]
                resultado["partes"]["reu"] = todas_partes[1:]
            elif todas_partes:
                pass
    
    return resultado


class AASPClient:
    def __init__(self):
        self.base_url = "https://intimacaoapi.aasp.org.br"
        self.api_key = settings.aasp_api_key
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def get_intimacoes(
        self,
        data: Optional[date] = None,
        diferencial: bool = False
    ) -> List[dict]:
        params = {
            "chave": self.api_key,
            "diferencial": str(diferencial).lower()
        }
        if data:
            params["data"] = data.strftime("%Y-%m-%d")
        
        url = f"{self.base_url}/api/Associado/intimacao/json"
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        
        result = response.json()
        intimacoes = result.get("intimacoes", [])
        
        parsed = []
        for item in intimacoes:
            jornal = item.get("jornal", {})
            texto = item.get("textoPublicacao", "")
            dados_processo = parse_dados_processo(texto)
            
            parsed.append({
                "numero_processo": item.get("numeroUnicoProcesso"),
                "conteudo": texto,
                "titulo": item.get("titulo"),
                "diario_oficial": jornal.get("nomeJornal"),
                "data_disponibilizacao": jornal.get("dataDisponibilizacao_Publicacao"),
                "codigo_relacionamento": item.get("codigoRelacionamento"),
                "numero_publicacao": item.get("numeroPublicacao"),
                "vara": dados_processo["vara"],
                "comarca": dados_processo["comarca"],
                "partes": dados_processo["partes"],
            })
        
        return parsed
    
    async def get_jornais_com_intimacoes(self, qtde_dias: int = 30) -> List[dict]:
        params = {
            "chave": self.api_key,
            "qtdeDias": qtde_dias
        }
        
        url = f"{self.base_url}/api/Associado/intimacao/GetJornaisComIntimacoes/json"
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        
        result = response.json()
        return result.get("datas", [])
    
    async def get_intimacoes_por_periodo(self, dias: int = 30) -> List[dict]:
        todas_intimacoes = []
        hoje = date.today()
        
        for i in range(dias):
            data = hoje - timedelta(days=i)
            try:
                intimacoes = await self.get_intimacoes(data=data)
                todas_intimacoes.extend(intimacoes)
            except Exception as e:
                print(f"Erro ao buscar {data}: {e}")
        
        return todas_intimacoes
    
    async def close(self):
        await self.client.aclose()


aasp_client = AASPClient()
