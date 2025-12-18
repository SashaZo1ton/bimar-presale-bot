#!/usr/bin/env python3
"""
🤖 JARVIS - BIMAR Presale Intelligence System
Advanced AI-powered presale assistant for BIMAR sales team.
Inspired by Iron Man's JARVIS - Just A Rather Very Intelligent System.
Version 2.1 - With interactive menu system
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
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    FSInputFile, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
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

# In-memory storage for user tasks history
user_tasks_history: Dict[int, List[Dict]] = {}
user_settings: Dict[int, Dict] = {}

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


class SettingsForm(StatesGroup):
    waiting_for_setting = State()


class JarvisMenus:
    """JARVIS menu keyboards."""
    
    @staticmethod
    def get_main_menu() -> ReplyKeyboardMarkup:
        """Main menu with Reply keyboard."""
        return ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text="🚀 Новый анализ"),
                    KeyboardButton(text="📊 Мои задачи")
                ],
                [
                    KeyboardButton(text="⚙️ Настройки"),
                    KeyboardButton(text="📈 Статус")
                ],
                [
                    KeyboardButton(text="📖 Справка")
                ]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
    
    @staticmethod
    def get_goal_keyboard() -> ReplyKeyboardMarkup:
        """Goal selection keyboard."""
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🎯 Вводная/квалификация")],
                [KeyboardButton(text="🚀 Согласование пилота")],
                [KeyboardButton(text="💼 ТКП")],
                [KeyboardButton(text="🔙 Главное меню")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    
    @staticmethod
    def get_settings_inline() -> InlineKeyboardMarkup:
        """Settings inline keyboard."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⚡ Quick Mode: ВКЛ" if QUICK_MODE else "⚡ Quick Mode: ВЫКЛ",
                        callback_data="toggle_quick_mode"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔔 Уведомления",
                        callback_data="settings_notifications"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🌐 Язык интерфейса",
                        callback_data="settings_language"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Назад",
                        callback_data="back_to_menu"
                    )
                ]
            ]
        )
    
    @staticmethod
    def get_task_actions(task_id: str) -> InlineKeyboardMarkup:
        """Task actions inline keyboard."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Повторить",
                        callback_data=f"repeat_task:{task_id}"
                    ),
                    InlineKeyboardButton(
                        text="📥 Скачать все",
                        callback_data=f"download_all:{task_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🗑️ Удалить",
                        callback_data=f"delete_task:{task_id}"
                    )
                ]
            ]
        )
    
    @staticmethod
    def get_back_to_menu() -> InlineKeyboardMarkup:
        """Back to menu button."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Главное меню",
                        callback_data="back_to_menu"
                    )
                ]
            ]
        )
    
    @staticmethod
    def get_cancel_keyboard() -> ReplyKeyboardMarkup:
        """Cancel operation keyboard."""
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        )


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
    def format_welcome(user_name: str = "сэр") -> str:
        greeting = random.choice(JARVIS_GREETINGS)
        return f"""
╔══════════════════════════════════════╗
║  🤖 J.A.R.V.I.S. - BIMAR SYSTEM     ║
║  Just A Rather Very Intelligent      ║
║  Sales-assistant                     ║
╚══════════════════════════════════════╝

{greeting}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 **Возможности системы:**

• 🚀 Анализ компании по URL
• 📊 Генерация 7 документов
• 💰 Расчет ROI
• 📋 Подготовка к встрече

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Выберите действие в меню ниже 👇
"""

    @staticmethod
    def format_new_analysis_prompt() -> str:
        return """
🚀 **НОВЫЙ АНАЛИЗ**

┌─────────────────────────────────────┐
│ Отправьте URL сайта компании        │
│ для запуска пресейл-аналитики       │
└─────────────────────────────────────┘

📎 Пример: https://company.com

💡 Я проанализирую компанию и подготовлю
   полный пакет документов за 3-7 минут
"""

    @staticmethod
    def format_url_received(url: str) -> str:
        return f"""
🔍 **Цель обнаружена**

┌─────────────────────────────────────┐
│ 🌐 {url[:35]}{'...' if len(url) > 35 else ''}
└─────────────────────────────────────┘

Сканирование инициировано...
"""

    @staticmethod
    def format_goal_selection() -> str:
        return """
📋 **Уточните параметры миссии**

Выберите цель предстоящей встречи:

┌─────────────────────────────────────┐
│ 🎯 **Вводная / Квалификация**       │
│    Первый контакт с клиентом        │
├─────────────────────────────────────┤
│ 🚀 **Согласование пилота**          │
│    Обсуждение пилотного проекта     │
├─────────────────────────────────────┤
│ 💼 **ТКП**                          │
│    Техническо-коммерческое          │
│    предложение                      │
└─────────────────────────────────────┘
"""

    @staticmethod
    def format_constraints_request() -> str:
        return """
🔒 **Ограничения и требования**

Укажите специфические требования клиента:

• on-prem (без облака)
• ИБ требования
• Камеры/видеонаблюдение
• Интеграции
• Другие ограничения

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Отправьте **"-"** если ограничений нет
"""

    @staticmethod
    def format_processing_start(url: str, goal: str, constraints: str) -> str:
        return f"""
⚡ **JARVIS активирован**

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
    def format_task_created(task_id: str) -> str:
        return f"""
✅ **Задача создана**

┌─────────────────────────────────────┐
│ 🆔 ID: {task_id[:20]}...
│ 📡 Статус: В обработке
└─────────────────────────────────────┘

⏳ Ожидаемое время: **3-7 минут**

Я сообщу, когда документы будут готовы.
"""

    @staticmethod
    def format_progress(status: str, elapsed_seconds: int) -> str:
        minutes = int(elapsed_seconds // 60)
        seconds = int(elapsed_seconds % 60)
        
        phases = ["Сбор данных", "Анализ", "Генерация", "Финализация"]
        current_phase_idx = min(int(elapsed_seconds / 90), 3)
        current_phase = phases[current_phase_idx]
        
        progress_bar = "█" * (current_phase_idx + 1) + "░" * (3 - current_phase_idx)
        
        return f"""
🔄 **Обработка запроса**

┌─────────────────────────────────────┐
│ ⏱️ Время: {minutes:02d}:{seconds:02d}
│ 📊 Прогресс: [{progress_bar}]
│ 🔧 Этап: {current_phase}
└─────────────────────────────────────┘
"""

    @staticmethod
    def format_files_ready(file_count: int) -> str:
        return f"""
📦 **Пакет документов готов**

Обнаружено файлов: **{file_count}**

⬇️ Начинаю передачу...
"""

    @staticmethod
    def format_file_sent(filename: str, description: str, index: int, total: int) -> str:
        return f"📄 [{index}/{total}] {description}"

    @staticmethod
    def format_completion(files_sent: int, total_expected: int, elapsed_time: str, company_name: str = "") -> str:
        status = "✅ ПОЛНЫЙ" if files_sent >= total_expected else f"⚠️ ЧАСТИЧНЫЙ ({files_sent}/{total_expected})"
        
        return f"""
╔══════════════════════════════════════╗
║  ✅ МИССИЯ ВЫПОЛНЕНА                ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│ 🏢 Компания: {company_name[:25] if company_name else 'Анализ завершен'}
│ 📊 Статус: {status}
│ 📁 Файлов: {files_sent}
│ ⏱️ Время: {elapsed_time}
└─────────────────────────────────────┘

{random.choice(JARVIS_SUCCESS)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Используйте меню для нового анализа 👇
"""

    @staticmethod
    def format_my_tasks(tasks: List[Dict]) -> str:
        if not tasks:
            return """
📊 **МОИ ЗАДАЧИ**

┌─────────────────────────────────────┐
│ 📭 История пуста                    │
│                                     │
│ Запустите первый анализ через       │
│ кнопку "🚀 Новый анализ"            │
└─────────────────────────────────────┘
"""
        
        tasks_text = """
📊 **МОИ ЗАДАЧИ**

┌─────────────────────────────────────┐
│ 📋 Последние запросы:               │
└─────────────────────────────────────┘

"""
        for i, task in enumerate(tasks[-5:], 1):  # Last 5 tasks
            status_icon = "✅" if task.get("status") == "completed" else "⏳" if task.get("status") == "running" else "❌"
            date = task.get("date", "")
            url = task.get("url", "")[:30]
            tasks_text += f"{i}. {status_icon} {url}{'...' if len(task.get('url', '')) > 30 else ''}\n"
            tasks_text += f"   📅 {date}\n\n"
        
        tasks_text += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 Нажмите на задачу для действий
"""
        return tasks_text

    @staticmethod
    def format_settings(user_id: int) -> str:
        settings = user_settings.get(user_id, {})
        quick_mode = settings.get("quick_mode", QUICK_MODE)
        notifications = settings.get("notifications", True)
        
        return f"""
⚙️ **НАСТРОЙКИ**

┌─────────────────────────────────────┐
│ ⚡ Quick Mode: {'✅ ВКЛ' if quick_mode else '❌ ВЫКЛ'}
│    Пропуск вопросов о цели/огр.     │
├─────────────────────────────────────┤
│ 🔔 Уведомления: {'✅ ВКЛ' if notifications else '❌ ВЫКЛ'}
│    Оповещения о статусе             │
├─────────────────────────────────────┤
│ 🌐 Язык: Русский                    │
└─────────────────────────────────────┘

Выберите параметр для изменения 👇
"""

    @staticmethod
    def format_status() -> str:
        return f"""
╔══════════════════════════════════════╗
║  📈 СТАТУС СИСТЕМЫ                  ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│ 🟢 JARVIS: **Онлайн**               │
│ 🟢 Manus API: **Подключен**         │
│ 🟢 Telegram: **Активен**            │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ ⏰ Время: {datetime.now().strftime('%H:%M:%S')}
│ 📅 Дата: {datetime.now().strftime('%d.%m.%Y')}
│ 🔧 Версия: 2.1
└─────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JARVIS v2.1 | BIMAR SYSTEM
"""

    @staticmethod
    def format_help() -> str:
        return """
╔══════════════════════════════════════╗
║  📖 СПРАВКА JARVIS                  ║
╚══════════════════════════════════════╝

🎮 **ГЛАВНОЕ МЕНЮ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 **Новый анализ** → Запуск пресейла
📊 **Мои задачи** → История запросов
⚙️ **Настройки** → Параметры бота
📈 **Статус** → Состояние системы
📖 **Справка** → Эта страница

📋 **КАК ИСПОЛЬЗОВАТЬ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Нажмите "🚀 Новый анализ"
2. Отправьте URL сайта компании
3. Выберите цель встречи
4. Укажите ограничения (или "-")
5. Дождитесь генерации (3-7 мин)
6. Получите 7 документов

📦 **ГЕНЕРИРУЕМЫЕ ДОКУМЕНТЫ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Deal_Brief.pdf
🗺️ Use_Case_Map.xlsx
💰 ROI_Calc.xlsx
📝 Pilot_SOW.docx
🎯 MAP.xlsx
📊 Mini_Deck.pptx
📚 Sources.md

⌨️ **КОМАНДЫ:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
/start → Перезапуск бота
/help → Справка
/cancel → Отмена операции

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JARVIS v2.1 | BIMAR SYSTEM
"""

    @staticmethod
    def format_error(error_type: str, details: str = "") -> str:
        return f"""
⚠️ **Системное уведомление**

┌─────────────────────────────────────┐
│ ❌ Ошибка: {error_type}
│ 📝 {details[:35] if details else 'Попробуйте позже'}
└─────────────────────────────────────┘

Рекомендации:
• Проверьте URL
• Попробуйте снова через минуту
• Используйте меню для навигации
"""

    @staticmethod
    def format_access_denied() -> str:
        return """
⛔ **ДОСТУП ЗАПРЕЩЁН**

┌─────────────────────────────────────┐
│ Ваш ID не авторизован в системе.   │
│ Обратитесь к администратору.       │
└─────────────────────────────────────┘
"""

    @staticmethod
    def format_cancel() -> str:
        return """
🛑 **Операция отменена**

Система готова к новому запросу.
Используйте меню для навигации 👇
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
        """Extract files from task response."""
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


def get_user_quick_mode(user_id: int) -> bool:
    """Get user's quick mode setting."""
    settings = user_settings.get(user_id, {})
    return settings.get("quick_mode", QUICK_MODE)


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
    """Poll task status until completion."""
    start_time = datetime.now()
    last_update_time = start_time
    ui = JarvisUI()
    
    while True:
        elapsed = (datetime.now() - start_time).total_seconds()
        
        if elapsed > TASK_TIMEOUT:
            logger.error(f"Task {task_id} timeout after {elapsed}s")
            try:
                await status_message.edit_text(
                    ui.format_error("Таймаут", "Время ожидания истекло"),
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass
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
                try:
                    await status_message.edit_text(
                        ui.format_error("Ошибка Manus", "Задача завершилась с ошибкой"),
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
                return None
            
            time_since_update = (datetime.now() - last_update_time).total_seconds()
            if time_since_update >= 30:
                try:
                    await status_message.edit_text(
                        ui.format_progress(status, elapsed),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    last_update_time = datetime.now()
                except Exception:
                    pass
            
            await asyncio.sleep(POLLING_INTERVAL)
        
        except Exception as e:
            logger.error(f"Error polling task: {e}")
            await asyncio.sleep(POLLING_INTERVAL)


# ==================== HANDLERS ====================

async def start_handler(message: types.Message, state: FSMContext):
    """Handle /start command."""
    user_id = message.from_user.id
    ui = JarvisUI()
    menus = JarvisMenus()
    
    if not is_user_allowed(user_id):
        await message.answer(ui.format_access_denied())
        return
    
    await state.clear()
    user_name = message.from_user.first_name or "сэр"
    await message.answer(
        ui.format_welcome(user_name),
        reply_markup=menus.get_main_menu(),
        parse_mode=ParseMode.MARKDOWN
    )


async def menu_handler(message: types.Message, state: FSMContext):
    """Handle main menu button presses."""
    user_id = message.from_user.id
    ui = JarvisUI()
    menus = JarvisMenus()
    
    if not is_user_allowed(user_id):
        await message.answer(ui.format_access_denied())
        return
    
    text = message.text
    
    if text == "🚀 Новый анализ":
        await state.clear()
        await message.answer(
            ui.format_new_analysis_prompt(),
            reply_markup=menus.get_cancel_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        await state.set_state(PresaleForm.waiting_for_url)
    
    elif text == "📊 Мои задачи":
        tasks = user_tasks_history.get(user_id, [])
        await message.answer(
            ui.format_my_tasks(tasks),
            reply_markup=menus.get_main_menu(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif text == "⚙️ Настройки":
        await message.answer(
            ui.format_settings(user_id),
            reply_markup=menus.get_settings_inline(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif text == "📈 Статус":
        await message.answer(
            ui.format_status(),
            reply_markup=menus.get_main_menu(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif text == "📖 Справка":
        await message.answer(
            ui.format_help(),
            reply_markup=menus.get_main_menu(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif text == "🔙 Главное меню":
        await state.clear()
        await message.answer(
            "🏠 Главное меню",
            reply_markup=menus.get_main_menu()
        )
    
    elif text == "❌ Отмена":
        await state.clear()
        await message.answer(
            ui.format_cancel(),
            reply_markup=menus.get_main_menu(),
            parse_mode=ParseMode.MARKDOWN
        )


async def url_handler(message: types.Message, state: FSMContext):
    """Handle company URL input."""
    user_id = message.from_user.id
    ui = JarvisUI()
    menus = JarvisMenus()
    
    if not is_user_allowed(user_id):
        return
    
    # Check for cancel
    if message.text in ["❌ Отмена", "🔙 Главное меню"]:
        await state.clear()
        await message.answer(
            ui.format_cancel(),
            reply_markup=menus.get_main_menu(),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    url = message.text.strip()
    
    if not url.startswith(("http://", "https://")):
        await message.answer(
            ui.format_error("Неверный формат", "URL должен начинаться с http:// или https://"),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await state.update_data(url=url)
    await message.answer(
        ui.format_url_received(url),
        parse_mode=ParseMode.MARKDOWN
    )
    
    if get_user_quick_mode(user_id):
        await state.update_data(goal="вводная/квалификация", constraints="неизвестно")
        await state.set_state(PresaleForm.processing)
        await process_presale(message, state)
    else:
        await message.answer(
            ui.format_goal_selection(),
            reply_markup=menus.get_goal_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        await state.set_state(PresaleForm.waiting_for_goal)


async def goal_handler(message: types.Message, state: FSMContext):
    """Handle goal selection."""
    user_id = message.from_user.id
    ui = JarvisUI()
    menus = JarvisMenus()
    
    if not is_user_allowed(user_id):
        return
    
    if message.text == "🔙 Главное меню":
        await state.clear()
        await message.answer(
            "🏠 Главное меню",
            reply_markup=menus.get_main_menu()
        )
        return
    
    goal = message.text.strip()
    goal = goal.replace("🎯 ", "").replace("🚀 ", "").replace("💼 ", "")
    
    await state.update_data(goal=goal)
    await message.answer(
        ui.format_constraints_request(),
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
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
    ui = JarvisUI()
    menus = JarvisMenus()
    start_time = datetime.now()
    
    try:
        data = await state.get_data()
        url = data.get("url")
        goal = data.get("goal", "вводная/квалификация")
        constraints = data.get("constraints", "неизвестно")
        
        await message.answer(
            ui.format_processing_start(url, goal, constraints),
            parse_mode=ParseMode.MARKDOWN
        )
        
        prompt = build_prompt_adapter(url, goal, constraints)
        client = ManusAPIClient(MANUS_API_KEY, MANUS_BASE_URL)
        
        task_response = client.create_task(prompt, MANUS_PROJECT_ID)
        task_id = task_response.get("task_id")
        
        if not task_id:
            await message.answer(
                ui.format_error("Ошибка API", "Не удалось создать задачу"),
                reply_markup=menus.get_main_menu(),
                parse_mode=ParseMode.MARKDOWN
            )
            await state.clear()
            return
        
        # Save to history
        if user_id not in user_tasks_history:
            user_tasks_history[user_id] = []
        user_tasks_history[user_id].append({
            "task_id": task_id,
            "url": url,
            "goal": goal,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "status": "running"
        })
        
        status_message = await message.answer(
            ui.format_task_created(task_id),
            parse_mode=ParseMode.MARKDOWN
        )
        
        task_data = await wait_for_task_completion(client, task_id, user_id, bot, status_message)
        
        if not task_data:
            # Update history
            for task in user_tasks_history.get(user_id, []):
                if task.get("task_id") == task_id:
                    task["status"] = "failed"
            await state.clear()
            return
        
        # Update history
        for task in user_tasks_history.get(user_id, []):
            if task.get("task_id") == task_id:
                task["status"] = "completed"
        
        files = client.extract_files_from_response(task_data)
        
        if not files:
            await message.answer(
                ui.format_error("Нет файлов", "В ответе не найдены документы"),
                reply_markup=menus.get_main_menu(),
                parse_mode=ParseMode.MARKDOWN
            )
            await state.clear()
            return
        
        await message.answer(
            ui.format_files_ready(len(files)),
            parse_mode=ParseMode.MARKDOWN
        )
        
        downloaded_files = {}
        total_files = len(files)
        
        for idx, file_info in enumerate(files, 1):
            filename = file_info["name"]
            file_url = file_info["url"]
            
            description = EXPECTED_ARTIFACTS.get(filename, f"📄 {filename}")
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
        
        elapsed = datetime.now() - start_time
        elapsed_str = f"{int(elapsed.total_seconds() // 60)}:{int(elapsed.total_seconds() % 60):02d}"
        
        await message.answer(
            ui.format_completion(len(downloaded_files), len(EXPECTED_ARTIFACTS), elapsed_str),
            reply_markup=menus.get_main_menu(),
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error in process_presale: {e}")
        await message.answer(
            ui.format_error("Системная ошибка", str(e)[:50]),
            reply_markup=menus.get_main_menu(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    finally:
        await state.clear()


async def settings_callback_handler(callback: CallbackQuery):
    """Handle settings inline button callbacks."""
    user_id = callback.from_user.id
    ui = JarvisUI()
    menus = JarvisMenus()
    
    if not is_user_allowed(user_id):
        await callback.answer("Доступ запрещен")
        return
    
    data = callback.data
    
    if data == "toggle_quick_mode":
        if user_id not in user_settings:
            user_settings[user_id] = {}
        current = user_settings[user_id].get("quick_mode", QUICK_MODE)
        user_settings[user_id]["quick_mode"] = not current
        
        await callback.message.edit_text(
            ui.format_settings(user_id),
            reply_markup=menus.get_settings_inline(),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer(f"Quick Mode: {'ВКЛ' if not current else 'ВЫКЛ'}")
    
    elif data == "settings_notifications":
        if user_id not in user_settings:
            user_settings[user_id] = {}
        current = user_settings[user_id].get("notifications", True)
        user_settings[user_id]["notifications"] = not current
        
        await callback.message.edit_text(
            ui.format_settings(user_id),
            reply_markup=menus.get_settings_inline(),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer(f"Уведомления: {'ВКЛ' if not current else 'ВЫКЛ'}")
    
    elif data == "settings_language":
        await callback.answer("Русский язык установлен по умолчанию")
    
    elif data == "back_to_menu":
        await callback.message.edit_text(
            "🏠 Используйте меню ниже для навигации",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()


async def help_handler(message: types.Message):
    """Handle /help command."""
    user_id = message.from_user.id
    ui = JarvisUI()
    menus = JarvisMenus()
    
    if not is_user_allowed(user_id):
        await message.answer(ui.format_access_denied())
        return
    
    await message.answer(
        ui.format_help(),
        reply_markup=menus.get_main_menu(),
        parse_mode=ParseMode.MARKDOWN
    )


async def cancel_handler(message: types.Message, state: FSMContext):
    """Handle /cancel command."""
    user_id = message.from_user.id
    ui = JarvisUI()
    menus = JarvisMenus()
    
    if not is_user_allowed(user_id):
        return
    
    await state.clear()
    await message.answer(
        ui.format_cancel(),
        reply_markup=menus.get_main_menu(),
        parse_mode=ParseMode.MARKDOWN
    )


async def main():
    """Main bot function."""
    
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
    logger.info("🤖 JARVIS v2.1 - BIMAR Presale Intelligence System")
    logger.info("=" * 50)
    logger.info(f"Manus API URL: {MANUS_BASE_URL}")
    logger.info(f"Project ID: {MANUS_PROJECT_ID}")
    logger.info(f"Quick Mode (default): {QUICK_MODE}")
    
    if ALLOWED_USER_IDS:
        logger.info(f"Allowed users: {ALLOWED_USER_IDS}")
    else:
        logger.info("All users allowed")
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Command handlers
    dp.message.register(start_handler, Command("start"))
    dp.message.register(help_handler, Command("help"))
    dp.message.register(cancel_handler, Command("cancel"))
    
    # Menu button handlers (must be before state handlers)
    dp.message.register(menu_handler, F.text.in_([
        "🚀 Новый анализ",
        "📊 Мои задачи",
        "⚙️ Настройки",
        "📈 Статус",
        "📖 Справка",
        "🔙 Главное меню",
        "❌ Отмена"
    ]))
    
    # State handlers
    dp.message.register(url_handler, PresaleForm.waiting_for_url)
    dp.message.register(goal_handler, PresaleForm.waiting_for_goal)
    dp.message.register(constraints_handler, PresaleForm.waiting_for_constraints)
    
    # Callback handlers
    dp.callback_query.register(settings_callback_handler)
    
    logger.info("🚀 JARVIS is starting...")
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
