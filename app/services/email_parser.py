"""Parser de emails OAB-ES (Recorte Digital) → lista de intimacoes.

Formato dos emails (Webjur Brasil / OAB-ES):
- Cada publicacao esta entre marcadores HTML:
    <!--Inicio publicacao;;Processo:XXXX-->
    ... HTML com campos estruturados ...
    <!--Fim publicacao;;Processo:NNNNNNN-NN.AAAA.J.TR.OOOO-->

- Campos estruturados (sempre nesse formato):
    <B>Publicacao: 1</B>
    <B>Data de Disponibilizacao:</B> DD/MM/YYYY
    <b>Data de Publicacao:</b> DD/MM/YYYY
    <b>Jornal:</b> Diario Oficial XXX
    <b>Caderno:</b> XXX
    <b>Local:</b> ... - <Comarca> - <Vara>
    <b>Pagina:</b> NNNNNN
    <texto da intimacao com partes, ordem, identificador PJe>

Output: lista de dicts no MESMO formato que AASPClient.get_intimacoes(),
para que o pipeline downstream funcione sem modificacao.
"""
import re
import logging
from typing import List, Dict
from datetime import date
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# CNJ regex (mesmo de extract_processo_numero em scheduler/jobs.py)
CNJ_REGEX = re.compile(r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}')

# Markers de bloco de publicacao
BLOCK_REGEX = re.compile(
    r'<!--Inicio publicacao;;Processo:[^>]*-->'
    r'(.*?)'
    r'<!--Fim publicacao;;Processo:([^>]*?)-->',
    re.DOTALL | re.IGNORECASE
)


def _br_date_to_iso(br_date: str) -> str:
    """DD/MM/YYYY -> YYYY-MM-DD. Retorna string vazia se invalido."""
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', br_date or "")
    if not m:
        return ""
    d, mo, y = m.groups()
    return f"{y}-{mo}-{d}"


def _extract_field(text: str, *patterns: str) -> str:
    """Tenta varios regex e retorna o primeiro match (group 1) limpo."""
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _parse_local(local: str) -> Dict[str, str]:
    """Local OAB-ES → vara + comarca.

    Exemplo: 'DJEN - Diario de Justica Eletronico Nacional - TJES - Vila Velha - Comarca da Capital - 4ª Vara de Familia'
    """
    if not local:
        return {"vara": "", "comarca": ""}

    parts = [p.strip() for p in local.split(" - ") if p.strip()]
    vara = ""
    comarca = ""

    # Heuristica: vara contem "vara", "juizado" ou "secretaria"
    for p in parts:
        pl = p.lower()
        if any(k in pl for k in ("vara ", "juizado", "secretaria", "secao", "turma")):
            vara = p
        elif "comarca" in pl and not comarca:
            comarca = p

    # Fallback comarca: primeira parte que nao seja "diario"/sigla/"djen"
    if not comarca:
        for p in parts:
            pl = p.lower()
            if not any(k in pl for k in ("diario", "djen", "djes", "tj", "stj", "stf", "tribunal")) \
               and "vara" not in pl and "juizado" not in pl:
                comarca = p
                break

    return {"vara": vara, "comarca": comarca}


def _parse_partes(texto_intimacao: str) -> Dict[str, list]:
    """Extrai polo ativo/passivo do texto da intimacao.

    Heuristica:
    1. POLO ATIVO:/POLO PASSIVO: (mais explicitos)
    2. Fallback: REQUERENTE:/REQUERIDO: pegando ate proxima palavra-chave
    3. Filtra textos narrativos (cuida-se, verifico, que ...)
    """
    autor = []
    reu = []

    # Stops comuns que indicam fim do nome de uma parte
    STOPS = r'POLO PASSIVO|POLO ATIVO|ADVOGADO|REQUERIDO|REQUERENTE|R[EÉ]U|OAB|INTIMACAO|DECISAO|DESPACHO|SENTENCA|DEMANDA|cuida-se|verifico|trata-se|que,'
    NARRATIVE = re.compile(r'^(que|cuida|verifico|trata|nos|em|a)\b', re.IGNORECASE)

    def _clean_value(val: str) -> str:
        v = val.strip().rstrip(":, ")
        if "segredo" in v.lower()[:30]:
            return "EM SEGREDO DE JUSTIÇA"
        return v[:200]

    m_ativo = re.search(
        rf'POLO ATIVO:\s*(.+?)(?=\s+(?:{STOPS})\b|$)',
        texto_intimacao,
        re.IGNORECASE | re.DOTALL,
    )
    if m_ativo:
        v = _clean_value(m_ativo.group(1))
        if v and not NARRATIVE.match(v):
            autor = [v]

    m_passivo = re.search(
        rf'POLO PASSIVO:\s*(.+?)(?=\s+(?:{STOPS})\b|$)',
        texto_intimacao,
        re.IGNORECASE | re.DOTALL,
    )
    if m_passivo:
        v = _clean_value(m_passivo.group(1))
        if v and not NARRATIVE.match(v):
            reu = [v]

    # Fallback REQUERENTE / REQUERIDO
    if not autor:
        m = re.search(
            rf'REQUERENTE:?\s*([A-ZÀ-Ÿ][^\n<]{{2,150}}?)(?=\s+(?:{STOPS})\b|$)',
            texto_intimacao,
            re.IGNORECASE,
        )
        if m:
            v = _clean_value(m.group(1))
            if v and len(v) > 3 and not NARRATIVE.match(v):
                autor = [v]

    if not reu:
        m = re.search(
            rf'REQUERIDO:?\s*([A-ZÀ-Ÿ][^\n<]{{2,150}}?)(?=\s+(?:{STOPS})\b|$)',
            texto_intimacao,
            re.IGNORECASE,
        )
        if m:
            v = _clean_value(m.group(1))
            if v and len(v) > 3 and not NARRATIVE.match(v):
                reu = [v]

    return {"autor": autor, "reu": reu}


def parse_oab_es_email(body_html: str, body_text: str = "", subject: str = "") -> List[Dict]:
    """Parse email OAB-ES Recorte Digital → lista de intimacoes.

    Retorna lista no MESMO formato que AASPClient.get_intimacoes():
        [{numero_processo, conteudo, titulo, diario_oficial,
          data_disponibilizacao, vara, comarca, partes}]

    Lista vazia se email nao tem publicacoes.
    """
    if not body_html:
        return []

    # Skip emails de notificacao "0 publicacoes"
    if "Não foi localizada qualquer publicação" in body_html:
        return []

    blocks = BLOCK_REGEX.findall(body_html)
    if not blocks:
        return []

    intimacoes = []
    for block_html, cnj_marker in blocks:
        # ── 1. Numero CNJ ──
        # Prioridade: marker FIM (formatado) → regex no texto bruto
        numero = ""
        cnj_marker_clean = (cnj_marker or "").strip()
        if CNJ_REGEX.fullmatch(cnj_marker_clean):
            numero = cnj_marker_clean
        else:
            # Tenta extrair do HTML do bloco
            m = CNJ_REGEX.search(block_html)
            if m:
                numero = m.group(0)

        # ── 2. Texto limpo do bloco ──
        bsoup = BeautifulSoup(block_html, "html.parser")
        text_clean = bsoup.get_text(separator=" ", strip=True)
        # Remove multi-spaces
        text_clean = re.sub(r'\s+', ' ', text_clean)

        # ── 3. Campos estruturados ──
        data_disp = _extract_field(
            text_clean,
            r'Data de Disponibiliza[çc][aã]o:?\s*(\d{2}/\d{2}/\d{4})',
        )
        data_pub = _extract_field(
            text_clean,
            r'Data de Publica[çc][aã]o:?\s*(\d{2}/\d{2}/\d{4})',
        )
        jornal = _extract_field(
            text_clean,
            r'Jornal:\s*(.+?)\s*(?:Caderno:|Local:|$)',
        )
        caderno = _extract_field(
            text_clean,
            r'Caderno:\s*(.+?)\s*(?:Local:|P[áa]gina:|$)',
        )
        local = _extract_field(
            text_clean,
            r'Local:\s*(.+?)\s*(?:P[áa]gina:|Intima[çc][aã]o\b|$)',
        )
        pagina = _extract_field(
            text_clean,
            r'P[áa]gina:\s*(\d+)',
        )

        # ── 4. Conteudo da intimacao ──
        # Comeca depois de "Pagina: NNNN" ou da palavra "Intimacao"
        m_conteudo = re.search(
            r'(?:P[áa]gina:\s*\d+\s*)?(Intima[çc][aã]o\b.+?)(?=\s*(?:Total de Publica|<!--|$))',
            text_clean,
            re.DOTALL | re.IGNORECASE,
        )
        conteudo = ""
        if m_conteudo:
            conteudo = m_conteudo.group(1).strip()
        else:
            # Fallback: tudo apos "Pagina:"
            m_fb = re.search(r'P[áa]gina:\s*\d+\s*(.+)', text_clean, re.DOTALL)
            if m_fb:
                conteudo = m_fb.group(1).strip()
            else:
                conteudo = text_clean[:5000]

        # Se nao achou CNJ ainda, tenta no conteudo
        if not numero:
            m = CNJ_REGEX.search(conteudo or text_clean)
            if m:
                numero = m.group(0)

        # ── 5. Vara / comarca / partes ──
        local_meta = _parse_local(local)
        partes = _parse_partes(conteudo)

        intimacao = {
            "numero_processo": numero,
            "conteudo": conteudo[:10000],  # cap em 10k chars
            "titulo": f"{jornal or 'OAB-ES'} - {data_disp}".strip(" -"),
            "diario_oficial": jornal or "OAB-ES Recorte Digital",
            "caderno": caderno,
            "data_disponibilizacao": _br_date_to_iso(data_disp),
            "data_publicacao": _br_date_to_iso(data_pub),
            "pagina": pagina,
            "vara": local_meta["vara"],
            "comarca": local_meta["comarca"],
            "partes": partes,
        }
        intimacoes.append(intimacao)

    return intimacoes
