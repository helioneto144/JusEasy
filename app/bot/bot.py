import asyncio
import logging
from telegram.ext import Application
from app.config import get_settings
from app.bot.handlers import setup_handlers

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.app = None
    
    async def initialize(self):
        if not self.token:
            logger.warning("Telegram bot token not configured")
            return
        
        logger.info("Initializing Telegram bot...")
        self.app = Application.builder().token(self.token).build()
        setup_handlers(self.app)
        await self.app.initialize()
        logger.info("Telegram bot initialized")
    
    async def start(self):
        if self.app:
            await self.app.start()
            await self.app.updater.start_polling()
            logger.info("Telegram bot started polling")
    
    async def stop(self):
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
    
    async def send_message(self, text: str, parse_mode: str = "HTML"):
        if self.app and self.chat_id:
            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode
            )


bot = TelegramBot()
