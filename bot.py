#!/usr/bin/env python3
"""
🤖 JARVIS - BIMAR Presale Intelligence System
Advanced AI-powered presale assistant for BIMAR sales team.
Inspired by Iron Man's JARVIS - Just A Rather Very Intelligent System.
"""

import asyncio
import os
import json
import logging
import random
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
from aiogram.types import (
    FSInputFile, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.enums import ParseMode


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

# Expected artifacts with descriptions
EXPECTED_ARTIFACTS = {
    "Deal_Brief.pdf": "📋 Краткое описание сделки",
    "Use_Case_Map.xlsx": "🗺️ Карта сценариев использования",
    "ROI_Calc.xlsx": "💰 Калькулятор ROI",
    "Pilot_SOW.docx": "📝 ТЗ на пилотный проект",
    "MAP.xlsx": "🎯 Mutual Action Plan",
    "Mini_Deck.pptx": "📊 Мини-презентация",
    "Sources.md": "📚 Источники и ссылки"
}

# JARVIS-style messages
JARVIS_GREETINGS = [
    "Добрый день, сэр. Система JARVIS активирована.",
    "Приветствую вас. JARVIS к вашим услугам.",
    "Система инициализирована. Готов к работе, сэр.",
    "JARVIS онлайн. Чем могу помочь?",
]

JARVIS_PROCESSING = [
    "Анализирую данные компании...",
    "Сканирую открытые источники...",
    "Обрабатываю информацию...",
    "Формирую аналитику...",
    "Генерирую документы...",
]

JARVIS_SUCCESS = [
    "Миссия выполнена, сэр.",
    "Задача успешно завершена.",
    "Все системы в норме. Пакет готов.",
    "Операция прошла успешно.",
]

JARVIS_WAITING = [
    "⏳ Анализ в процессе... {progress}%",
    "🔄 Обработка данных... {progress}%",
    "⚡ Генерация артефактов... {progress}%",
    "🧠 ИИ работает... {progress}%",
]

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


class JarvisUI:
    """JARVIS-style UI components and messages."""
    
    @staticmethod
    def get_greeting() -> str:
        return random.choice(JARVIS_GREETINGS)
    
    @staticmethod
    def get_processing_message() -> str:
        return random.choice(JARVIS_PROCESSING)
    
    @staticmethod
    def get_success_message() -> str:
        return random.choice(JARVIS_SUCCESS)
    
    @staticmethod
    def get_waiting_message(progress: int = 0) -> str:
        msg = random.choice(JARVIS_WAITING)
        return msg.format(progress=progress)
    
    @staticmethod
    def format_welcome() -> str:
        return """
╔══════════════════════════════════════╗
║  🤖 J.A.R.V.I.S. - BIMAR SYSTEM     ║
║  Just A Rather Very Intelligent      ║
║  Sales-assistant                     ║
╚══════════════════════════════════════╝

Добро пожаловать в систему пресейл-аналитики BIMAR.

Я помогу вам подготовить полный пакет документов для встречи с клиентом за несколько минут.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 Что я умею:
• Анализировать компанию по URL
• Определять отрасль и специфику
• Генерировать 7 ключевых документов
• Рассчитывать ROI и сценарии

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📎 Отправьте URL сайта компании для начала анализа.
"""

    @staticmethod
    def format_url_received(url: str) -> str:
        return f"""
🔍 Цель обнаружена

┌─────────────────────────────────────┐
│ 🌐 {url[:35]}{'...' if len(url) > 35 else ''}
└─────────────────────────────────────┘

Сканирование инициировано...
"""

    @staticmethod
    def format_goal_selection() -> str:
        return """
📋 Уточните параметры миссии

Выберите цель предстоящей встречи:

┌─────────────────────────────────────┐
│ 1️⃣  Вводная / Квалификация         │
│     Первый контакт с клиентом       │
├─────────────────────────────────────┤
│ 2️⃣  Согласование пилота            │
│     Обсуждение пилотного проекта    │
├─────────────────────────────────────┤
│ 3️⃣  ТКП                            │
│     Техническо-коммерческое         │
│     предложение                     │
└─────────────────────────────────────┘
"""

    @staticmethod
    def format_constraints_request() -> str:
        return """
🔒 Ограничения и требования

Укажите специфические требования клиента:

• on-prem (без облака)
• ИБ требования
• Камеры/видеонаблюдение
• Интеграции
• Другие ограничения

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Отправьте "-" если ограничений нет
"""

    @staticmethod
    def format_processing_start(url: str, goal: str, constraints: str) -> str:
        return f"""
⚡ JARVIS активирован

┌─────────────────────────────────────┐
│ 🎯 МИССИЯ: Пресейл-аналитика       │
├─────────────────────────────────────┤
│ 🌐 Цель: {url[:30]}{'...' if len(url) > 30 else ''}
│ 📋 Этап: {goal[:25]}
│ 🔒 Ограничения: {constraints[:20]}{'...' if len(constraints) > 20 else ''}
└─────────────────────────────────────┘

🔄 Запуск анализа...
"""

    @staticmethod
    def format_task_created(task_id: str, task_url: str) -> str:
        return f"""
✅ Задача создана в системе

┌─────────────────────────────────────┐
│ 🆔 ID: {task_id[:20]}...
│ 🔗 Мониторинг: Manus Dashboard
└─────────────────────────────────────┘

⏳ Ожидаемое время: 3-7 минут

Я сообщу, когда документы будут готовы.
"""

    @staticmethod
    def format_progress(status: str, elapsed_seconds: int, phase: str = "") -> str:
        minutes = int(elapsed_seconds // 60)
        seconds = int(elapsed_seconds % 60)
        
        # Progress bar
        phases = ["Сбор данных", "Анализ", "Генерация", "Финализация"]
        current_phase_idx = min(int(elapsed_seconds / 90), 3)
        current_phase = phases[current_phase_idx]
        
        progress_bar = "█" * (current_phase_idx + 1) + "░" * (3 - current_phase_idx)
        
        return f"""
🔄 Обработка запроса

┌─────────────────────────────────────┐
│ ⏱️ Время: {minutes:02d}:{seconds:02d}
│ 📊 Прогресс: [{progress_bar}]
│ 🔧 Этап: {current_phase}
└─────────────────────────────────────┘
"""

    @staticmethod
    def format_files_ready(file_count: int) -> str:
        return f"""
📦 Пакет документов готов

Обнаружено файлов: {file_count}

⬇️ Начинаю передачу...
"""

    @staticmethod
    def format_file_sent(filename: str, description: str, index: int, total: int) -> str:
        return f"📄 [{index}/{total}] {description}"

    @staticmethod
    def format_completion(files_sent: int, total_expected: int, elapsed_time: str) -> str:
        status = "✅ ПОЛНЫЙ" if files_sent >= total_expected else f"⚠️ ЧАСТИЧНЫЙ ({files_sent}/{total_expected})"
        
        return f"""
╔══════════════════════════════════════╗
║  ✅ МИССИЯ ВЫПОЛНЕНА                ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│ 📊 Статус: {status}
│ 📁 Файлов: {files_sent}
│ ⏱️ Время: {elapsed_time}
└─────────────────────────────────────┘

{random.choice(JARVIS_SUCCESS)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Отправьте новый URL для следующего анализа
   или /help для справки
"""

    @staticmethod
    def format_error(error_type: str, details: str = "") -> str:
        return f"""
⚠️ Системное уведомление

┌─────────────────────────────────────┐
│ ❌ Ошибка: {error_type}
│ 📝 {details[:35] if details else 'Попробуйте позже'}
└─────────────────────────────────────┘

Рекомендации:
• Проверьте URL
• Попробуйте снова через минуту
• Используйте /cancel для сброса
"""

    @staticmethod
    def format_help() -> str:
        return """
╔══════════════════════════════════════╗
║  📖 СПРАВКА JARVIS                  ║
╚══════════════════════════════════════╝

🎮 КОМАНДЫ:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
/start   → Начать работу
/help    → Эта справка
/cancel  → Отменить операцию
/status  → Статус системы

📋 КАК ИСПОЛЬЗОВАТЬ:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Отправьте URL сайта компании
2. Выберите цель встречи
3. Укажите ограничения (или "-")
4. Дождитесь генерации (3-7 мин)
5. Получите 7 документов

📦 ГЕНЕРИРУЕМЫЕ ДОКУМЕНТЫ:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Deal_Brief.pdf
   Краткое описание сделки

🗺️ Use_Case_Map.xlsx
   Карта сценариев использования

💰 ROI_Calc.xlsx
   Калькулятор возврата инвестиций

📝 Pilot_SOW.docx
   ТЗ на пилотный проект

🎯 MAP.xlsx
   Mutual Action Plan

📊 Mini_Deck.pptx
   Мини-презентация

📚 Sources.md
   Источники и ссылки

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JARVIS v2.0 | BIMAR SYSTEM
"""

    @staticmethod
    def format_status() -> str:
        return f"""
╔══════════════════════════════════════╗
║  📊 СТАТУС СИСТЕМЫ                  ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│ 🟢 JARVIS: Онлайн
│ 🟢 Manus API: Подключен
│ 🟢 Telegram: Активен
└─────────────────────────────────────┘

⏰ Время сервера: {datetime.now().strftime('%H:%M:%S')}
📅 Дата: {datetime.now().strftime('%d.%m.%Y')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JARVIS v2.0 | Готов к работе
"""

    @staticmethod
    def format_access_denied() -> str:
        return """
⛔ ДОСТУП ЗАПРЕЩЁН

┌─────────────────────────────────────┐
│ Ваш ID не авторизован в системе.   │
│ Обратитесь к администратору.       │
└─────────────────────────────────────┘
"""

    @staticmethod
    def format_cancel() -> str:
        return """
🛑 Операция отменена

Система готова к новому запросу.
Отправьте URL для начала анализа.
"""


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
            logger.info(f"Task created response: {data}")
            logger.info(f"Task ID: {data.get('task_id')}")
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
                if "fileUrl" in obj and "fileName" in obj:
                    files.append({
                        "url": obj["fileUrl"],
                        "name": obj["fileName"],
                        "mimeType": obj.get("mimeType", "application/octet-stream")
                    })
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
    
    # Sanitize filename
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
    if not safe_filename:
        safe_filename = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    filepath = download_dir / safe_filename
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status == 200:
                        with open(filepath, 'wb') as f:
                            f.write(await resp.read())
                        logger.info(f"Downloaded: {safe_filename}")
                        return filepath
                    else:
                        logger.warning(f"Failed to download {safe_filename}: HTTP {resp.status}")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout downloading {safe_filename} (attempt {attempt + 1})")
        except Exception as e:
            logger.error(f"Error downloading {safe_filename}: {e}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)
    
    return None


async def wait_for_task_completion(
    client: ManusAPIClient, 
    task_id: str, 
    user_id: int, 
    bot: Bot,
    status_message: types.Message
) -> Optional[Dict[str, Any]]:
    """Poll task status until completion with live updates."""
    start_time = datetime.now()
    last_update_time = start_time
    ui = JarvisUI()
    
    while True:
        elapsed = (datetime.now() - start_time).total_seconds()
        
        if elapsed > TASK_TIMEOUT:
            logger.error(f"Task {task_id} timeout after {elapsed}s")
            await status_message.edit_text(
                ui.format_error("Таймаут", "Время ожидания истекло")
            )
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
                await status_message.edit_text(
                    ui.format_error("Ошибка Manus", "Задача завершилась с ошибкой")
                )
                return None
            
            # Update progress message every 30 seconds
            time_since_update = (datetime.now() - last_update_time).total_seconds()
            if time_since_update >= 30:
                try:
                    await status_message.edit_text(
                        ui.format_progress(status, elapsed)
                    )
                    last_update_time = datetime.now()
                except Exception:
                    pass  # Ignore edit errors
            
            await asyncio.sleep(POLLING_INTERVAL)
        
        except Exception as e:
            logger.error(f"Error polling task: {e}")
            await asyncio.sleep(POLLING_INTERVAL)


# Handlers
async def start_handler(message: types.Message, state: FSMContext):
    """Handle /start command."""
    user_id = message.from_user.id
    ui = JarvisUI()
    
    if not is_user_allowed(user_id):
        await message.answer(ui.format_access_denied())
        return
    
    await state.clear()
    await message.answer(ui.format_welcome(), reply_markup=ReplyKeyboardRemove())
    await state.set_state(PresaleForm.waiting_for_url)


async def url_handler(message: types.Message, state: FSMContext):
    """Handle company URL input."""
    user_id = message.from_user.id
    ui = JarvisUI()
    
    if not is_user_allowed(user_id):
        return
    
    url = message.text.strip()
    
    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        await message.answer(
            ui.format_error("Неверный формат", "URL должен начинаться с http:// или https://")
        )
        return
    
    await state.update_data(url=url)
    await message.answer(ui.format_url_received(url))
    
    if QUICK_MODE:
        await state.update_data(goal="вводная/квалификация", constraints="неизвестно")
        await state.set_state(PresaleForm.processing)
        await process_presale(message, state)
    else:
        goal_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🎯 Вводная/квалификация")],
                [KeyboardButton(text="🚀 Согласование пилота")],
                [KeyboardButton(text="💼 ТКП")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(ui.format_goal_selection(), reply_markup=goal_keyboard)
        await state.set_state(PresaleForm.waiting_for_goal)


async def goal_handler(message: types.Message, state: FSMContext):
    """Handle goal selection."""
    user_id = message.from_user.id
    ui = JarvisUI()
    
    if not is_user_allowed(user_id):
        return
    
    # Clean goal text from emojis
    goal = message.text.strip()
    goal = goal.replace("🎯 ", "").replace("🚀 ", "").replace("💼 ", "")
    
    await state.update_data(goal=goal)
    await message.answer(ui.format_constraints_request(), reply_markup=ReplyKeyboardRemove())
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
    """Process presale request with JARVIS-style updates."""
    user_id = message.from_user.id
    bot = message.bot
    ui = JarvisUI()
    start_time = datetime.now()
    
    try:
        data = await state.get_data()
        url = data.get("url")
        goal = data.get("goal", "вводная/квалификация")
        constraints = data.get("constraints", "неизвестно")
        
        # Send processing start message
        await message.answer(ui.format_processing_start(url, goal, constraints))
        
        # Build prompt
        prompt = build_prompt_adapter(url, goal, constraints)
        
        # Create Manus API client
        client = ManusAPIClient(MANUS_API_KEY, MANUS_BASE_URL)
        
        # Create task
        task_response = client.create_task(prompt, MANUS_PROJECT_ID)
        task_id = task_response.get("task_id")
        task_url = task_response.get("task_url", "")
        
        if not task_id:
            await message.answer(ui.format_error("Ошибка API", "Не удалось создать задачу"))
            await state.clear()
            return
        
        # Send task created message (this will be updated with progress)
        status_message = await message.answer(ui.format_task_created(task_id, task_url))
        
        # Wait for completion with live updates
        task_data = await wait_for_task_completion(client, task_id, user_id, bot, status_message)
        
        if not task_data:
            await state.clear()
            return
        
        # Extract files
        files = client.extract_files_from_response(task_data)
        
        if not files:
            await message.answer(ui.format_error("Нет файлов", "В ответе не найдены документы"))
            await state.clear()
            return
        
        await message.answer(ui.format_files_ready(len(files)))
        
        # Download and send files
        downloaded_files = {}
        total_files = len(files)
        
        for idx, file_info in enumerate(files, 1):
            filename = file_info["name"]
            file_url = file_info["url"]
            
            # Get description for known files
            description = EXPECTED_ARTIFACTS.get(filename, f"📄 {filename}")
            
            # Download file
            filepath = await download_file(file_url, filename)
            
            if filepath and filepath.exists():
                try:
                    file_input = FSInputFile(str(filepath))
                    caption = ui.format_file_sent(filename, description, idx, total_files)
                    await bot.send_document(user_id, file_input, caption=caption)
                    downloaded_files[filename] = True
                    logger.info(f"Sent file: {filename}")
                except Exception as e:
                    logger.error(f"Error sending file {filename}: {e}")
        
        # Calculate elapsed time
        elapsed = datetime.now() - start_time
        elapsed_str = f"{int(elapsed.total_seconds() // 60)}:{int(elapsed.total_seconds() % 60):02d}"
        
        # Send completion message
        await message.answer(
            ui.format_completion(len(downloaded_files), len(EXPECTED_ARTIFACTS), elapsed_str)
        )
        
    except Exception as e:
        logger.error(f"Error in process_presale: {e}")
        await message.answer(ui.format_error("Системная ошибка", str(e)[:50]))
    
    finally:
        await state.clear()


async def help_handler(message: types.Message):
    """Handle /help command."""
    user_id = message.from_user.id
    ui = JarvisUI()
    
    if not is_user_allowed(user_id):
        await message.answer(ui.format_access_denied())
        return
    
    await message.answer(ui.format_help())


async def status_handler(message: types.Message):
    """Handle /status command."""
    user_id = message.from_user.id
    ui = JarvisUI()
    
    if not is_user_allowed(user_id):
        await message.answer(ui.format_access_denied())
        return
    
    await message.answer(ui.format_status())


async def cancel_handler(message: types.Message, state: FSMContext):
    """Handle /cancel command."""
    user_id = message.from_user.id
    ui = JarvisUI()
    
    if not is_user_allowed(user_id):
        return
    
    await state.clear()
    await message.answer(ui.format_cancel(), reply_markup=ReplyKeyboardRemove())


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
    
    logger.info("=" * 50)
    logger.info("🤖 JARVIS - BIMAR Presale Intelligence System")
    logger.info("=" * 50)
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
    dp.message.register(status_handler, Command("status"))
    dp.message.register(cancel_handler, Command("cancel"))
    
    # State handlers
    dp.message.register(url_handler, PresaleForm.waiting_for_url)
    dp.message.register(goal_handler, PresaleForm.waiting_for_goal)
    dp.message.register(constraints_handler, PresaleForm.waiting_for_constraints)
    
    logger.info("🚀 JARVIS is starting...")
    
    # Start polling
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
