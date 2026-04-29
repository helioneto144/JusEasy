from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    database_url: str

    aasp_api_key: str
    aasp_api_url: str = "https://intimacaoapi.aasp.org.br"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    polling_interval_hours: int = 3
    timezone: str = "America/Sao_Paulo"

    # URL pública da aplicação (usada nos botões do Telegram)
    app_url: str = "http://localhost:8000"

    # IA — Qwen via OpenAI-compatible API
    ai_api_key: str = ""
    ai_base_url: str = "https://coding-intl.dashscope.aliyuncs.com/v1"
    ai_model: str = "qwen-plus"

    # Groq — resumo rápido de intimações
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    # Webhook (alternativa via Cloudflare Email Worker — opcional)
    webhook_secret: str = ""

    # Gmail IMAP (captura de intimações via email)
    gmail_user: str = ""                          # ex: heliomenezesneto@gmail.com
    gmail_app_password: str = ""                  # App Password do Gmail (16 chars sem espaços)
    gmail_imap_host: str = "imap.gmail.com"
    gmail_imap_label: str = "OAB-ES"              # label que o filtro Gmail aplica

    # Feature flags — captura de intimações
    aasp_enabled: bool = True       # legacy, será desligado quando OAB-ES funcionar
    oab_es_enabled: bool = False    # processamento via email da OAB-ES

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
