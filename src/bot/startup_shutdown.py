import logging
from src.bot.config import ADMIN_CHAT_ID, WEBHOOK_URL
from src.bot.bot_setup import bot, dp
from aiogram import Dispatcher
from src.middlewares.forward_to_admin_middleware import ForwardToAdminMiddleware
from src.utils.background_tasks import sync_proxy_connections
import asyncio

async def on_startup(dp):
    if WEBHOOK_URL:  # If WEBHOOK_URL is set, use webhook mode
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text='Bot has been started with WEBHOOK')
        logging.info("Bot has been started with WEBHOOK")
        check_for_missed_updates()
        await bot.set_webhook(url=WEBHOOK_URL)
    else:  # If WEBHOOK_URL is not set, use long polling mode
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text='Bot has been started (long polling)')
    asyncio.create_task(sync_proxy_connections())

async def on_shutdown(dp):
    # Close the ForwardToAdminMiddleware
    for middleware in dp.middleware.applications:
        if isinstance(middleware, ForwardToAdminMiddleware):
            await middleware.close()
    await bot.send_message(chat_id=ADMIN_CHAT_ID, text='Bot has been stopped')
