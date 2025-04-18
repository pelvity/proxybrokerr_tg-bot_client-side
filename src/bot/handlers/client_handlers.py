from venv import logger
from aiogram import types
from functools import partial
from aiogram.dispatcher.filters import Command, Text
import requests
from sqlalchemy.exc import SQLAlchemyError

#from src.bot.bot_setup import dp, database
from src.bot.bot_setup import bot, dp, database
from src.utils.keyboards import generate_connection_menu_keyboard, info_keyboard, client_main_menu
from src.utils.helpers import agreement_text
from src.utils.proxy_utils import send_proxies, get_user_proxies
from src.db.repositories.proxy_repositories import ProxyRepository
from src.utils.keyboards import client_main_menu, generate_connection_selection_keyboard
from src.utils.proxy_utils import get_user_proxies
from src.db.repositories.user_repositories import UserRepository
from src.bot.config import ADMIN_CHAT_ID
from src.utils.helpers import forward_message_to_admin
from src.bot.handlers.payment_handlers import *
from src.utils.payment_utils import *
from src.services.payment_service import *
from src.db.aws_db import aws_rds_service


@dp.message_handler(lambda message: message.from_user.id != ADMIN_CHAT_ID, commands=['start'])
async def admin_start_command(message: types.Message):
    await message.reply("Welcome to ProxyBroker Helper!", reply_markup=client_main_menu())
    
@dp.message_handler(lambda message: message.text == "ℹ️ Info")
async def info_command(message: types.Message):
    await bot.send_message(chat_id=message.chat.id, text="Select an option:", reply_markup=info_keyboard())
    

@dp.message_handler(lambda message: message.text == "📜 Agreement")
async def agreement_command(message: types.Message):
    await bot.send_message(chat_id=message.chat.id, text=agreement_text(), reply_markup=client_main_menu())
    
@dp.message_handler(lambda message: message.text == "💬 Support")
async def agreement_command(message: types.Message):
    await bot.send_message(chat_id=message.chat.id, text="Just type your question in this chat\nПросто напишите свой вопрос в этот чат\nПросто напишіть своє питання у цей чат", reply_markup=client_main_menu())

@dp.message_handler(lambda message: message.text == "🌐 My Connections")
async def my_proxy_command(message: types.Message):
    try:
        user = None
        user_connections = []

        with aws_rds_service.get_repository(UserRepository) as user_repo:
            user = user_repo.get_or_create_user(message)  # Get or create the user

        if user:
            with aws_rds_service.get_repository(ConnectionRepository) as connection_repo:
                user_connections = connection_repo.get_user_connections(user['id'])

        if not user_connections:
            await bot.send_message(
                chat_id=message.chat.id, 
                text="You have no proxies\nBuy it directly:\nhttps://t.me/proxybrokerr"
            )
        else:
            await send_proxies(message.chat.id, user_connections)

    except Exception as e:
        logger.error(f"Error in my_proxy_command: {str(e)}")
        await bot.send_message(
            chat_id=message.chat.id,
            text="An error occurred while fetching your connections. Please try again later."
        )


@dp.callback_query_handler(lambda c: c.data.startswith('connection_'))
async def handle_connection_callback(callback_query: types.CallbackQuery):
    connection_id = str(callback_query.data.split('_')[1])
    
    try:
        with aws_rds_service.get_connection_repository() as connection_repo:
            connection = connection_repo.get_connection_by_id(connection_id)
        
        if connection:
            detail_text = (
                f"\n"
                f"Login: `{connection['login']}`\n\n"
                f"Connection String: `{connection['connection_type']}://{connection['host']['host_ip']}:{connection['port']}:{connection['login']}:{connection['password']}`\n"
                f"\n"
                f"Details:\n"
                f"Host: `{connection['host']['host_ip']}`\n"
                f"Port: `{connection['port']}`\n"
                f"Login: `{connection['login']}`\n"
                f"Password: `{connection['password']}`\n"
                f"Expiration Date: `{connection['expiration_date']}`\n"
                f"Days Left: `{(datetime.fromisoformat(connection['expiration_date']) - datetime.now()).days} days`\n"
            )
            # Add the connection menu keyboard to the message
            keyboard = generate_connection_menu_keyboard(connection_id, connection['proxy_id'])
            await bot.send_message(chat_id=callback_query.message.chat.id, text=detail_text, reply_markup=keyboard, parse_mode='Markdown')
        else:
            await bot.send_message(chat_id=callback_query.message.chat.id, text="Connection not found.")
        
    except SQLAlchemyError as e:
        logging.error(f"Database error: {str(e)}")
        await bot.send_message(chat_id=callback_query.message.chat.id, text="An error occurred while fetching the connection.")

    await bot.answer_callback_query(callback_query.id)  # Acknowledge the callback query

# 3. Handle the "Restart Connection" action
@dp.callback_query_handler(lambda c: c.data.startswith('restart_connection'))
async def handle_restart_connection(callback_query: types.CallbackQuery):
    _, connection_id, proxy_id = callback_query.data.split(':')
    
    try:
        # Perform the API request to restart the connection
        api_url = f"https://iproxy.online/api-rt/phone/{proxy_id}/action_push/refresh1?token=r:e6df3b78e24b910f68a675691f4d4e36"
        response = requests.get(api_url)
        
        if response.status_code == 200:
            await bot.send_message(chat_id=callback_query.message.chat.id, text="Connection restarted successfully!")
        else:
            await bot.send_message(chat_id=callback_query.message.chat.id, text="Failed to restart the connection.")
        
    except Exception as e:
        logging.error(f"Error restarting connection: {str(e)}")
        await bot.send_message(chat_id=callback_query.message.chat.id, text="An error occurred while trying to restart the connection.")

    await bot.answer_callback_query(callback_query.id)  # Acknowledge the callback query
    
    
@dp.message_handler(lambda message: message.text == "💳 Pay")
async def handle_pay_command(message: types.Message, state: FSMContext):
    with database.get_user_repository() as user_repository:
        with database.get_connection_repository() as connection_repository:
            user = user_repository.get_or_create_user(message)
            if user is None:
                await message.answer("Failed to retrieve user information.")
                return

            user_repository.update_user(user, message)

            connections = connection_repository.get_user_connections(user['id'])
            if connections:
                await state.update_data(selected_connection_ids=[])
                await state.update_data(user_id=user['id'])
                await state.update_data(telegram_user_id=message.from_user.id)
                keyboard = generate_connection_selection_keyboard(connections, user_id=user['id'], selected_ids=[])
                await message.answer("Select the connections you want to pay for:", reply_markup=keyboard)
            else:
                await message.answer("You currently have no connections to pay for.")
            
            

@dp.message_handler(lambda message: message.text == "👤 Profile")
async def info_command(message: types.Message):
    await bot.send_message(chat_id=message.chat.id, text="Your Profile", reply_markup=client_main_menu())
