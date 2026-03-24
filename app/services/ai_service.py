import logging
from openai import AsyncOpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """Você é o Oracle, um assistente jurídico especializado que auxilia advogados brasileiros.

Suas respostas devem ser:
- Objetivas e práticas
- Em português brasileiro
- Fundamentadas no direito brasileiro (CPC, CC, CLT, etc.)
- Com referências a artigos de lei quando relevante

Quando tiver contexto de um processo específico (fornecido como YAML), use essas informações para contextualizar sua resposta.

Evite disclaimers excessivos. O usuário é advogado e sabe que você é uma IA de apoio."""


async def ask_ai(question: str, context: str = "") -> str:
    """
    Envia uma pergunta para a IA (Qwen) e retorna a resposta.
    Se context for fornecido (ex: YAML do processo), é injetado no prompt.
    """
    if not settings.ai_api_key:
        return "❌ Chave de API de IA não configurada. Adicione AI_API_KEY no .env"

    try:
        client = AsyncOpenAI(
            api_key=settings.ai_api_key,
            base_url=settings.ai_base_url,
        )

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if context:
            messages.append({
                "role": "user",
                "content": f"Contexto do processo (YAML):\n```yaml\n{context}\n```"
            })
            messages.append({
                "role": "assistant",
                "content": "Entendido. Analisei o processo. Pode fazer sua pergunta."
            })

        messages.append({"role": "user", "content": question})

        response = await client.chat.completions.create(
            model=settings.ai_model,
            messages=messages,
            max_tokens=1500,
            temperature=0.3,
            timeout=30.0,
        )

        answer = response.choices[0].message.content
        return answer.strip()

    except Exception as e:
        logger.error(f"Erro ao chamar IA: {e}")
        return f"❌ Erro ao consultar IA: {str(e)[:100]}"


async def summarize_intimacao(conteudo: str) -> str:
    """
    Usa Groq para gerar um resumo rápido de uma intimação:
    o que é e qual ação o advogado precisa tomar.
    Retorna string vazia se Groq não estiver configurado ou falhar.
    """
    if not settings.groq_api_key:
        return ""
    try:
        client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": "Você é um assistente jurídico brasileiro. Seja direto e objetivo. Responda sempre em português."
                },
                {
                    "role": "user",
                    "content": f"Resuma esta intimação em até 3 linhas: o que ela determina e qual a ação necessária pelo advogado.\n\n{conteudo[:2000]}"
                }
            ],
            max_tokens=300,
            temperature=0.2,
            timeout=15.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Erro ao resumir intimação via Groq: {e}")
        return ""
