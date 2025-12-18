#!/usr/bin/env python3
"""
BIMAR Presale Bot - Telegram bot for generating presale artifacts via Manus API.
Accepts company URL and returns presale package (PDF, XLSX, DOCX, PPTX, MD).
"""

import asyncio
import os
import json
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime
from pathlib import Path
import aiohttp
import requests
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove


# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MANUS_API_KEY = os.getenv("MANUS_API_KEY")
MANUS_BASE_URL = os.getenv("MANUS_BASE_URL", "https://api.manus.ai")
MANUS_PROJECT_ID = os.getenv("MANUS_PROJECT_ID")
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS", "").split(",") if os.getenv("ALLOWED_USER_IDS") else None
QUICK_MODE = os.getenv("QUICK_MODE", "0") == "1"
TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT", "1500"))
POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "10"))

# Expected artifacts
EXPECTED_ARTIFACTS = {
    "Deal_Brief.pdf",
    "Use_Case_Map.xlsx",
    "ROI_Calc.xlsx",
    "Pilot_SOW.docx",
    "MAP.xlsx",
    "Mini_Deck.pptx",
    "Sources.md"
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FSM States
class PresaleForm(StatesGroup):
    waiting_for_url = State()
    waiting_for_goal = State()
    waiting_for_constraints = State()
    processing = State()


class ManusAPIClient:
    """Client for Manus API interactions."""
    
    def __init__(self, api_key: str, base_url: str = "https://api.manus.ai"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "API_KEY": api_key,
            "Content-Type": "application/json"
        }
    
    def create_task(self, prompt: str, project_id: str, agent_profile: str = "manus-1.6-lite") -> Dict[str, Any]:
        """Create a task in Manus API."""
        url = f"{self.base_url}/v1/tasks"
        payload = {
            "prompt": prompt,
            "projectId": project_id,
            "agentProfile": agent_profile
        }
        
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Task created: {data.get('id')}")
            return data
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            raise
    
    def get_task(self, task_id: str) -> Dict[str, Any]:
        """Get task status and results."""
        url = f"{self.base_url}/v1/tasks/{task_id}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting task {task_id}: {e}")
            raise
    
    @staticmethod
    def extract_files_from_response(response: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract files from task response (recursive search)."""
        files = []
        
        def search_files(obj):
            if isinstance(obj, dict):
                # Check if this dict has file properties
                if "fileUrl" in obj and "fileName" in obj:
                    files.append({
                        "url": obj["fileUrl"],
                        "name": obj["fileName"],
                        "mimeType": obj.get("mimeType", "application/octet-stream")
                    })
                # Recursively search in all values
                for value in obj.values():
                    search_files(value)
            elif isinstance(obj, list):
                for item in obj:
                    search_files(item)
        
        search_files(response)
        return files


def is_user_allowed(user_id: int) -> bool:
    """Check if user is in allowlist."""
    if ALLOWED_USER_IDS is None:
        return True
    return str(user_id) in ALLOWED_USER_IDS


def build_prompt_adapter(url: str, goal: str = "вводная/квалификация", constraints: str = "неизвестно") -> str:
    """Build PROMPT_ADAPTER_V1 for Manus task."""
    
    adapter = f"""Запусти пресейл-аналитику строго по мастер-инструкции проекта.

Заполни входные данные для текущего запуска:
- Компания: {{ИНФЕРИРУЙ ИЗ САЙТА, если несколько вариантов — укажи основной и альтернативы}}
- сайт: {url}
- Отрасль/вертикаль: {{ИНФЕРИРУЙ, если не уверен — 2–3 гипотезы}}
- География/юрконтур: {{ИНФЕРИРУЙ}}
- Валюта: {{ИНФЕРИРУЙ}}
- Цель встречи: {goal}
- Ограничения: {constraints} (если нет данных — сформируй вопросы и используй гипотезы)

КРИТИЧНО (контракт выхода):
1) Сгенерируй и приложи как ФАЙЛЫ (не просто текстом) строго эти артефакты с точными именами:
   - Deal_Brief.pdf
   - Use_Case_Map.xlsx
   - ROI_Calc.xlsx
   - Pilot_SOW.docx
   - MAP.xlsx
   - Mini_Deck.pptx
   - Sources.md
2) Если по какому-то файлу данных не хватает — всё равно создай файл, но пометь допущения/пустые поля и вынеси вопросы в конец.
3) Любой факт/цифра — со ссылкой и датой доступа; иначе помечай "Гипотеза".
4) Удерживай размер файлов минимальным (без тяжёлых скриншотов), чтобы каждый файл был < 50 MB.
5) В конце текстового ответа в чат дай список: "Файл → что внутри (1 строка)"."""
    
    return adapter


async def download_file(url: str, filename: str, max_retries: int = 3) -> Optional[Path]:
    """Download file from URL."""
    download_dir = Path("downloads")
    download_dir.mkdir(exist_ok=True)
    
    filepath = download_dir / filename
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status == 200:
                        with open(filepath, 'wb') as f:
                            f.write(await resp.read())
                        logger.info(f"Downloaded: {filename}")
                        return filepath
                    else:
                        logger.warning(f"Failed to download {filename}: HTTP {resp.status}")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout downloading {filename} (attempt {attempt + 1})")
        except Exception as e:
            logger.error(f"Error downloading {filename}: {e}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)
    
    return None


async def wait_for_task_completion(client: ManusAPIClient, task_id: str, user_id: int, bot: Bot) -> Optional[Dict[str, Any]]:
    """Poll task status until completion."""
    start_time = datetime.now()
    
    while True:
        elapsed = (datetime.now() - start_time).total_seconds()
        
        if elapsed > TASK_TIMEOUT:
            logger.error(f"Task {task_id} timeout after {elapsed}s")
            await bot.send_message(user_id, "⏱️ Время ожидания истекло. Попробуйте позже.")
            return None
        
        try:
            task_data = client.get_task(task_id)
            status = task_data.get("status")
            
            logger.info(f"Task {task_id} status: {status}")
            
            if status == "completed":
                logger.info(f"Task {task_id} completed successfully")
                return task_data
            elif status == "failed":
                logger.error(f"Task {task_id} failed")
                await bot.send_message(user_id, "❌ Задача в Manus завершилась с ошибкой. Попробуйте позже.")
                return None
            elif status == "processing":
                progress = task_data.get("progress", 0)
                await bot.send_message(user_id, f"⏳ Обработка... {progress}%")
            
            await asyncio.sleep(POLLING_INTERVAL)
        
        except Exception as e:
            logger.error(f"Error polling task: {e}")
            await asyncio.sleep(POLLING_INTERVAL)


# Handlers
async def start_handler(message: types.Message, state: FSMContext):
    """Handle /start command."""
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        await message.answer("❌ У вас нет доступа к этому боту.")
        return
    
    await message.answer(
        "👋 Добро пожаловать в BIMAR Presale Bot!\n\n"
        "Я помогу вам сгенерировать пресейл-пакет для компании.\n\n"
        "Отправьте URL компании (например: https://example.com)",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(PresaleForm.waiting_for_url)


async def url_handler(message: types.Message, state: FSMContext):
    """Handle company URL input."""
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        return
    
    url = message.text.strip()
    
    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        await message.answer("❌ Пожалуйста, отправьте корректный URL (начинается с http:// или https://)")
        return
    
    await state.update_data(url=url)
    
    if QUICK_MODE:
        # Skip questions in quick mode
        await state.update_data(goal="вводная/квалификация", constraints="неизвестно")
        await state.set_state(PresaleForm.processing)
        await process_presale(message, state)
    else:
        # Ask for goal
        goal_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Вводная/квалификация")],
                [KeyboardButton(text="Согласование пилота")],
                [KeyboardButton(text="ТКП")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer("📋 Выберите цель встречи:", reply_markup=goal_keyboard)
        await state.set_state(PresaleForm.waiting_for_goal)


async def goal_handler(message: types.Message, state: FSMContext):
    """Handle goal selection."""
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        return
    
    goal = message.text.strip()
    await state.update_data(goal=goal)
    
    await message.answer(
        "🔒 Укажите ограничения (например: on-prem, ИБ, камера, без облака и т.д.)\n"
        "Или отправьте '-' если ограничений нет:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(PresaleForm.waiting_for_constraints)


async def constraints_handler(message: types.Message, state: FSMContext):
    """Handle constraints input."""
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        return
    
    constraints = message.text.strip()
    if constraints == "-":
        constraints = "нет"
    
    await state.update_data(constraints=constraints)
    await state.set_state(PresaleForm.processing)
    await process_presale(message, state)


async def process_presale(message: types.Message, state: FSMContext):
    """Process presale request."""
    user_id = message.from_user.id
    bot = message.bot
    
    try:
        # Get data from state
        data = await state.get_data()
        url = data.get("url")
        goal = data.get("goal", "вводная/квалификация")
        constraints = data.get("constraints", "неизвестно")
        
        await message.answer("🚀 Начинаю обработку запроса...")
        
        # Build prompt
        prompt = build_prompt_adapter(url, goal, constraints)
        
        # Create Manus API client
        client = ManusAPIClient(MANUS_API_KEY, MANUS_BASE_URL)
        
        # Create task
        await message.answer("📤 Создаю задачу в Manus...")
        task_response = client.create_task(prompt, MANUS_PROJECT_ID)
        task_id = task_response.get("id")
        
        if not task_id:
            await message.answer("❌ Ошибка: не удалось создать задачу в Manus")
            await state.clear()
            return
        
        await message.answer(f"✅ Задача создана: `{task_id}`\n⏳ Ожидаю результатов...", parse_mode="Markdown")
        
        # Wait for completion
        task_data = await wait_for_task_completion(client, task_id, user_id, bot)
        
        if not task_data:
            await state.clear()
            return
        
        # Extract files
        files = client.extract_files_from_response(task_data)
        
        if not files:
            await message.answer("❌ В ответе не найдены файлы. Попробуйте позже.")
            await state.clear()
            return
        
        await message.answer(f"📦 Найдено файлов: {len(files)}\n⬇️ Загружаю файлы...")
        
        # Download and send files
        downloaded_files = {}
        missing_artifacts = set(EXPECTED_ARTIFACTS)
        
        for file_info in files:
            filename = file_info["name"]
            file_url = file_info["url"]
            
            # Track expected artifacts
            if filename in missing_artifacts:
                missing_artifacts.discard(filename)
            
            # Download file
            filepath = await download_file(file_url, filename)
            
            if filepath and filepath.exists():
                try:
                    # Send file to Telegram
                    file_input = FSInputFile(str(filepath))
                    await bot.send_document(user_id, file_input, caption=f"📄 {filename}")
                    downloaded_files[filename] = True
                    logger.info(f"Sent file: {filename}")
                except Exception as e:
                    logger.error(f"Error sending file {filename}: {e}")
                    await message.answer(f"⚠️ Не удалось отправить файл: {filename}")
        
        # Report missing artifacts
        if missing_artifacts:
            missing_list = "\n".join(f"- {f}" for f in sorted(missing_artifacts))
            await message.answer(
                f"⚠️ Отсутствуют файлы:\n{missing_list}\n\n"
                f"Отправлено файлов: {len(downloaded_files)}/{len(EXPECTED_ARTIFACTS)}"
            )
        else:
            await message.answer(f"✅ Все файлы успешно отправлены! ({len(downloaded_files)} файлов)")
        
        # Send summary
        summary = "📋 **Итоговый список файлов:**\n"
        for filename in sorted(downloaded_files.keys()):
            summary += f"✅ {filename}\n"
        
        await message.answer(summary, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error in process_presale: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
    
    finally:
        await state.clear()


async def help_handler(message: types.Message):
    """Handle /help command."""
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        return
    
    help_text = """
🤖 **BIMAR Presale Bot - Справка**

**Команды:**
/start - Начать работу
/help - Показать эту справку
/cancel - Отменить текущую операцию

**Как использовать:**
1. Отправьте /start
2. Введите URL компании
3. Выберите цель встречи (если не включен QUICK_MODE)
4. Укажите ограничения (если не включен QUICK_MODE)
5. Ожидайте результатов
6. Получите пресейл-пакет (7 файлов)

**Генерируемые файлы:**
- Deal_Brief.pdf
- Use_Case_Map.xlsx
- ROI_Calc.xlsx
- Pilot_SOW.docx
- MAP.xlsx
- Mini_Deck.pptx
- Sources.md

**Режимы:**
- QUICK_MODE=0: Бот задает вопросы (цель встречи, ограничения)
- QUICK_MODE=1: Автоматический режим без вопросов
"""
    await message.answer(help_text, parse_mode="Markdown")


async def cancel_handler(message: types.Message, state: FSMContext):
    """Handle /cancel command."""
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        return
    
    await state.clear()
    await message.answer("❌ Операция отменена.", reply_markup=ReplyKeyboardRemove())


async def main():
    """Main bot function."""
    
    # Validate configuration
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    
    if not MANUS_API_KEY:
        logger.error("MANUS_API_KEY not set")
        raise ValueError("MANUS_API_KEY environment variable is required")
    
    if not MANUS_PROJECT_ID:
        logger.error("MANUS_PROJECT_ID not set")
        raise ValueError("MANUS_PROJECT_ID environment variable is required")
    
    logger.info("Starting BIMAR Presale Bot...")
    logger.info(f"Manus API URL: {MANUS_BASE_URL}")
    logger.info(f"Project ID: {MANUS_PROJECT_ID}")
    logger.info(f"Quick Mode: {QUICK_MODE}")
    
    if ALLOWED_USER_IDS:
        logger.info(f"Allowed users: {ALLOWED_USER_IDS}")
    else:
        logger.info("All users allowed")
    
    # Initialize bot and dispatcher
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    
    # Register handlers
    dp.message.register(start_handler, Command("start"))
    dp.message.register(help_handler, Command("help"))
    dp.message.register(cancel_handler, Command("cancel"))
    
    # URL handler
    dp.message.register(url_handler, PresaleForm.waiting_for_url)
    
    # Goal handler
    dp.message.register(goal_handler, PresaleForm.waiting_for_goal)
    
    # Constraints handler
    dp.message.register(constraints_handler, PresaleForm.waiting_for_constraints)
    
    # Start polling
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
