#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  🤖 J.A.R.V.I.S. v3.0 - BIMAR Presale Intelligence System   ║
║  Just A Rather Very Intelligent Sales-assistant              ║
║                                                              ║
║  Telegram Bot для генерации пресейл-пакетов                 ║
║  с интеграцией Manus API                                    ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import asyncio
import aiohttp
import logging
import tempfile
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery, FSInputFile,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

# Определение состояний FSM для двухэтапного процесса
class PresaleStates(StatesGroup):
    """ФСМ состояния для пресейл-бота"""
    waiting_for_url = State()       # Ожидание URL сайта
    waiting_for_goal = State()      # Ожидание выбора цели
    analyzing = State()             # Этап 1: Анализ и создание досье
    selecting_docs = State()        # Этап 2: Выбор документов
    generating_docs = State()       # Этап 3: Генерация выбранных документов
    waiting_for_constraints = State()  # Ожидание ограничений
    processing = State()            # Обработка задачи Manus

# Типы документов для выбора
DOCUMENT_TYPES = {
    "dossier": {
        "id": "dossier",
        "name": "01_Досье_на_клиента",
        "filename": "01_Досье_на_клиента.docx",
        "format": "docx",
        "icon": "📋",
        "description": "Профиль компании, боли, ЛПР",
        "mandatory": True
    },
    "use_cases": {
        "id": "use_cases",
        "name": "02_Решения_BIMAR",
        "filename": "02_Решения_BIMAR.xlsx",
        "format": "xlsx",
        "icon": "🗺️",
        "description": "Карта модулей BimAR и сценариев"
    },
    "roi": {
        "id": "roi",
        "name": "03_Экономика_сделки",
        "filename": "03_Экономика_сделки.xlsx",
        "format": "xlsx",
        "icon": "💰",
        "description": "ROI калькулятор + стоимость пилота"
    },
    "sow": {
        "id": "sow",
        "name": "04_Пилот_ТЗ",
        "filename": "04_Пилот_ТЗ.docx",
        "format": "docx",
        "icon": "📝",
        "description": "Техзадание на пилот 90 дней"
    },
    "stakeholders": {
        "id": "stakeholders",
        "name": "05_ЛПР_и_квалификация",
        "filename": "05_ЛПР_и_квалификация.xlsx",
        "format": "xlsx",
        "icon": "🎯",
        "description": "Карта ЛПР + MEDDPICC"
    },
    "presentation": {
        "id": "presentation",
        "name": "06_Питч_для_клиента",
        "filename": "06_Питч_для_клиента.pptx",
        "format": "pptx",
        "icon": "📊",
        "description": "Презентация 10-12 слайдов"
    },
    "verification": {
        "id": "verification",
        "name": "07_Верификация",
        "filename": "07_Верификация.docx",
        "format": "docx",
        "icon": "✅",
        "description": "Чек-лист готовности пресейла"
    }
}

# Список документов для выбора (исключая обязательные)
SELECTABLE_DOCS = [k for k, v in DOCUMENT_TYPES.items() if not v.get("mandatory", False)]

# ═══════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MANUS_API_KEY = os.getenv("MANUS_API_KEY")
MANUS_PROJECT_ID = os.getenv("MANUS_PROJECT_ID", "YghG6cpo3udE8p2gcYzQfP")
MANUS_BASE_URL = os.getenv("MANUS_BASE_URL", "https://api.manus.ai")
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS", "")
QUICK_MODE_DEFAULT = os.getenv("QUICK_MODE", "0") == "1"
POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "10"))
TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT", "1500"))

VERSION = "3.0"
START_TIME = datetime.now()

# Проверка обязательных переменных
if not TELEGRAM_BOT_TOKEN:
    print("❌ ERROR: TELEGRAM_BOT_TOKEN not set")
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

if not MANUS_API_KEY:
    print("⚠️ WARNING: MANUS_API_KEY not set - API calls will fail")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# ХРАНИЛИЩЕ ДАННЫХ
# ═══════════════════════════════════════════════════════════════

user_tasks: Dict[int, List[Dict]] = {}
user_settings: Dict[int, Dict] = {}
stats = {
    "requests_today": 0,
    "successful": 0,
    "errors": 0,
    "files_sent": 0
}

# Кэш результатов по URL (домен -> данные задачи)
url_cache: Dict[str, Dict] = {}
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "24"))  # Время жизни кэша в часах

# Очередь задач для параллельной обработки
task_queue: asyncio.Queue = None  # Инициализируется при запуске
active_tasks: Dict[str, Dict] = {}  # task_id -> информация о задаче
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "3"))  # Макс параллельных задач

# Хранилище завершённых задач с документами (user_id -> [{task_id, domain, files, date}])
completed_tasks: Dict[int, List[Dict]] = {}

# ═══════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ БОТА
# ═══════════════════════════════════════════════════════════════

bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# ═══════════════════════════════════════════════════════════════
# КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════════

def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Новый анализ"), KeyboardButton(text="📊 Мои задачи")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📈 Статус")],
            [KeyboardButton(text="📖 Справка")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

def get_goals_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Вводная/квалификация", callback_data="goal_intro")],
            [InlineKeyboardButton(text="🚀 Согласование пилота", callback_data="goal_pilot")],
            [InlineKeyboardButton(text="💼 ТКП", callback_data="goal_tkp")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ]
    )

def get_settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    settings = get_user_settings(user_id)
    quick_mode = "✅" if settings.get("quick_mode", False) else "❌"
    notifications = "✅" if settings.get("notifications", True) else "❌"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⚡ Quick Mode {quick_mode}", callback_data="toggle_quick_mode")],
            [InlineKeyboardButton(text=f"🔔 Уведомления {notifications}", callback_data="toggle_notifications")],
            [InlineKeyboardButton(text="🌐 Язык", callback_data="settings_language")],
            [InlineKeyboardButton(text="🎯 Цель по умолчанию", callback_data="settings_default_goal")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ]
    )

def get_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
             InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")]
        ]
    )

def get_default_goal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭕ Не задана (спрашивать)", callback_data="default_goal_none")],
            [InlineKeyboardButton(text="🎯 Вводная/квалификация", callback_data="default_goal_intro")],
            [InlineKeyboardButton(text="🚀 Согласование пилота", callback_data="default_goal_pilot")],
            [InlineKeyboardButton(text="💼 ТКП", callback_data="default_goal_tkp")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")]
        ]
    )

def get_status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить статус", callback_data="refresh_status")],
            [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")]
        ]
    )

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    )

def get_tasks_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для выбора завершённых задач"""
    tasks = get_completed_tasks(user_id)
    buttons = []
    for i, task in enumerate(tasks[:5], 1):
        domain = task.get("domain", "unknown")[:15]
        task_id = task.get("task_id", "")
        buttons.append([InlineKeyboardButton(
            text=f"#{i} 📁 {domain}",
            callback_data=f"download_task_{task_id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cache_keyboard(domain: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора: использовать кэш или перегенерировать"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Использовать готовые документы", callback_data=f"use_cache_{domain}")],
            [InlineKeyboardButton(text="🔄 Сгенерировать заново", callback_data="regenerate")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ]
    )

def get_document_selector_keyboard(selected: set) -> InlineKeyboardMarkup:
    """Клавиатура для выбора документов с чекбоксами"""
    buttons = []
    
    for doc_id in SELECTABLE_DOCS:
        doc = DOCUMENT_TYPES.get(doc_id, {})
        icon = doc.get("icon", "📄")
        name = doc.get("name", doc_id)
        check = "✅" if doc_id in selected else "⬜"
        buttons.append([InlineKeyboardButton(
            text=f"{check} {icon} {name}",
            callback_data=f"toggle_doc_{doc_id}"
        )])
    
    # Кнопка "Выбрать все / Снять все"
    all_selected = len(selected) == len(SELECTABLE_DOCS)
    toggle_text = "❌ Снять все" if all_selected else "✅ Выбрать все"
    buttons.append([InlineKeyboardButton(text=toggle_text, callback_data="toggle_all_docs")])
    
    # Кнопка подтверждения
    buttons.append([InlineKeyboardButton(
        text=f"🚀 Создать выбранные ({len(selected)})",
        callback_data="confirm_docs" if selected else "noop"
    )])
    
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_selected_docs_summary(selected: set) -> str:
    """Формирует текстовое описание выбранных документов"""
    lines = []
    for doc_id in selected:
        doc = DOCUMENT_TYPES.get(doc_id, {})
        icon = doc.get("icon", "📄")
        name = doc.get("name", doc_id)
        lines.append(f"{icon} {name}")
    return "\n".join(lines) if lines else "Нет выбранных документов"

# ═══════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════

def get_user_settings(user_id: int) -> Dict:
    if user_id not in user_settings:
        user_settings[user_id] = {
            "quick_mode": QUICK_MODE_DEFAULT,
            "notifications": True,
            "language": "ru",
            "default_goal": None
        }
    return user_settings[user_id]

def get_user_tasks(user_id: int) -> List[Dict]:
    if user_id not in user_tasks:
        user_tasks[user_id] = []
    return user_tasks[user_id]

def add_user_task(user_id: int, task: Dict):
    tasks = get_user_tasks(user_id)
    tasks.insert(0, task)
    user_tasks[user_id] = tasks[:10]

def is_user_allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    allowed = [int(x.strip()) for x in ALLOWED_USER_IDS.split(",") if x.strip()]
    return user_id in allowed if allowed else True

def validate_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

def get_uptime() -> str:
    delta = datetime.now() - START_TIME
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}ч {minutes}м {seconds}с"

def get_progress_bar(percent: int, length: int = 10) -> str:
    filled = int(length * percent / 100)
    return "█" * filled + "░" * (length - filled)

# Функции кэширования
def get_cached_result(domain: str) -> Optional[Dict]:
    """Получить закэшированный результат по домену"""
    if domain in url_cache:
        cached = url_cache[domain]
        cache_time = datetime.fromisoformat(cached.get("cached_at", "2000-01-01"))
        if datetime.now() - cache_time < timedelta(hours=CACHE_TTL_HOURS):
            logger.info(f"Cache hit for {domain}")
            return cached
        else:
            # Кэш устарел
            del url_cache[domain]
            logger.info(f"Cache expired for {domain}")
    return None

def set_cached_result(domain: str, task_id: str, files: List[Dict]):
    """Сохранить результат в кэш"""
    url_cache[domain] = {
        "task_id": task_id,
        "files": files,
        "cached_at": datetime.now().isoformat()
    }
    logger.info(f"Cached result for {domain}")

# Функции работы с завершёнными задачами
def get_completed_tasks(user_id: int) -> List[Dict]:
    """Получить список завершённых задач пользователя"""
    if user_id not in completed_tasks:
        completed_tasks[user_id] = []
    return completed_tasks[user_id]

def add_completed_task(user_id: int, task_data: Dict):
    """Добавить завершённую задачу с файлами"""
    tasks = get_completed_tasks(user_id)
    tasks.insert(0, task_data)
    completed_tasks[user_id] = tasks[:20]  # Храним последние 20 задач
    logger.info(f"Added completed task for user {user_id}: {task_data.get('domain')}")

def get_task_by_id(user_id: int, task_id: str) -> Optional[Dict]:
    """Найти задачу по ID"""
    tasks = get_completed_tasks(user_id)
    for task in tasks:
        if task.get("task_id") == task_id:
            return task
    return None

# Этапы генерации с процентами
GENERATION_STAGES = [
    {"name": "Анализ сайта", "icon": "🔍", "start": 0, "end": 20},
    {"name": "Сбор данных", "icon": "📊", "start": 20, "end": 45},
    {"name": "Генерация документов", "icon": "📄", "start": 45, "end": 85},
    {"name": "Финализация", "icon": "✅", "start": 85, "end": 100}
]

def get_current_stage(percent: int) -> dict:
    """Определяет текущий этап по проценту"""
    for stage in GENERATION_STAGES:
        if stage["start"] <= percent < stage["end"]:
            return stage
    return GENERATION_STAGES[-1]

def get_stages_visual(percent: int) -> str:
    """Генерирует визуальное отображение этапов"""
    lines = []
    for stage in GENERATION_STAGES:
        if percent >= stage["end"]:
            status = "✅"
        elif percent >= stage["start"]:
            status = "⏳"
        else:
            status = "⬜"
        lines.append(f"{status} {stage['icon']} {stage['name']}")
    return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════
# СООБЩЕНИЯ JARVIS
# ═══════════════════════════════════════════════════════════════

def msg_welcome() -> str:
    return f"""╔══════════════════════════════════════╗
║  🤖 J.A.R.V.I.S. - BIMAR SYSTEM     ║
║  Just A Rather Very Intelligent      ║
║  Sales-assistant                     ║
╚══════════════════════════════════════╝

Добро пожаловать, сэр.

Я — ваш персональный ИИ-ассистент
для подготовки пресейл-материалов.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎮 Используйте меню ниже для навигации.

💡 Для быстрого старта нажмите
   «🚀 Новый анализ»

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JARVIS v{VERSION} | BIMAR SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

def msg_new_analysis() -> str:
    return """┌─────────────────────────────────────┐
│  🚀 ЗАПУСК ПРЕСЕЙЛ-АНАЛИТИКИ       │
└─────────────────────────────────────┘

Отправьте URL сайта целевой компании.

📎 Пример: https://company.com

💡 JARVIS проанализирует компанию и
   подготовит полный пакет документов

⏱️ Время генерации: 15-30 минут"""

def msg_url_accepted(domain: str) -> str:
    return f"""┌─────────────────────────────────────┐
│  ✅ URL ПРИНЯТ                      │
│  {domain[:35]:<35} │
└─────────────────────────────────────┘

🎯 Выберите цель встречи:"""

def msg_goal_accepted(goal: str) -> str:
    return f"""┌─────────────────────────────────────┐
│  ✅ ЦЕЛЬ УСТАНОВЛЕНА                │
│  {goal[:35]:<35} │
└─────────────────────────────────────┘

🔒 Укажите ограничения клиента:
   (on-prem, ИБ, камера, без облака и т.д.)

Или отправьте «-» если ограничений нет."""

def msg_processing_start() -> str:
    return """╔══════════════════════════════════════╗
║  🚀 ЗАПУСК АНАЛИЗА                  ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│ 📊 Статус: ИНИЦИАЛИЗАЦИЯ            │
│ ⏱️ Время: 00:00                     │
│ 🔧 Этап: Создание задачи            │
└─────────────────────────────────────┘

⏳ Подключение к Manus AI..."""

def msg_processing_progress(elapsed_min: int, elapsed_sec: int, stage: str, percent: int) -> str:
    progress = get_progress_bar(percent)
    return f"""╔══════════════════════════════════════╗
║  ⚙️ АНАЛИЗ В ПРОЦЕССЕ               ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│ ⏱️ Время: {elapsed_min:02d}:{elapsed_sec:02d}                       │
│ 📊 Прогресс: [{progress}] {percent}%       │
│ 🔧 Этап: {stage[:25]:<25} │
└─────────────────────────────────────┘

💡 Пожалуйста, подождите...
   JARVIS анализирует данные."""

def msg_processing_complete(elapsed: str, files_count: int) -> str:
    return f"""╔══════════════════════════════════════╗
║  ✅ МИССИЯ ВЫПОЛНЕНА                ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│ 📊 Статус: УСПЕШНО                  │
│ 📁 Файлов: {files_count}                        │
│ ⏱️ Время: {elapsed:<24} │
└─────────────────────────────────────┘

📦 Документы доставлены выше ⬆️

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Миссия выполнена, сэр.
Используйте меню для нового анализа 👇
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

def msg_help() -> str:
    return f"""╔══════════════════════════════════════╗
║  📖 СПРАВКА JARVIS                  ║
╚══════════════════════════════════════╝

🤖 О СИСТЕМЕ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JARVIS (Just A Rather Very Intelligent
Sales-assistant) — ваш персональный
ИИ-помощник для подготовки пресейлов.

🎮 ГЛАВНОЕ МЕНЮ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 Новый анализ → Запуск пресейла
📊 Мои задачи   → История запросов
⚙️ Настройки    → Параметры бота
📈 Статус       → Состояние системы
📖 Справка      → Эта страница

📋 КАК ИСПОЛЬЗОВАТЬ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1️⃣ Нажмите «🚀 Новый анализ»
2️⃣ Отправьте URL сайта компании
3️⃣ Выберите цель встречи
4️⃣ Дождитесь генерации (15-30 мин)
5️⃣ Получите 7 документов

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 ПРЕСЕЙЛ-ПАКЕТ (7 документов)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 01_Досье_на_клиента.pdf
   Комплексный анализ компании:
   отрасль, боли, ЛПР, точки входа

🗺️ 02_Решения_BIMAR.xlsx
   Карта use cases BIMAR для клиента
   с приоритизацией и оценкой

💰 03_Экономика_сделки.xlsx
   ROI-калькулятор: экономия,
   окупаемость, финансовый эффект

📝 04_Пилот_ТЗ.docx
   Готовое ТЗ: цели, scope, KPI,
   этапы, команда, риски

🎯 05_Лица_принимающие_решения.xlsx
   Stakeholder map: ЛПР, ЛВР,
   влияние, стратегия работы

📊 06_Питч_для_клиента.pptx
   Презентация для встречи:
   боли → решение → ROI → пилот

📚 07_Верификация.md
   Все источники информации
   для проверки данных

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 СОВЕТЫ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Используйте главный сайт компании
• Чем точнее URL, тем лучше анализ
• Укажите ограничения для точного ROI
• Quick Mode экономит время

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JARVIS v{VERSION} | BIMAR SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

def msg_status(user_id: int) -> str:
    settings = get_user_settings(user_id)
    uptime = get_uptime()
    quick_mode = "✅ ВКЛ" if settings.get("quick_mode") else "❌ ВЫКЛ"
    notifications = "✅ ВКЛ" if settings.get("notifications", True) else "❌ ВЫКЛ"
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    return f"""╔══════════════════════════════════════╗
║  📈 СТАТУС СИСТЕМЫ JARVIS           ║
╚══════════════════════════════════════╝

🕐 Время запроса: {now}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤖 ЯДРО JARVIS
┌─────────────────────────────────────┐
│ Статус:      🟢 ОНЛАЙН              │
│ Версия:      v{VERSION}                   │
│ Аптайм:      {uptime:<20} │
└─────────────────────────────────────┘

🔌 MANUS API
┌─────────────────────────────────────┐
│ Статус:      🟢 ПОДКЛЮЧЕНО          │
│ Endpoint:    api.manus.ai           │
│ Project ID:  {MANUS_PROJECT_ID[:20]:<20} │
└─────────────────────────────────────┘

📡 TELEGRAM API
┌─────────────────────────────────────┐
│ Статус:      🟢 АКТИВЕН             │
│ Username:    @bimar_presale_bot     │
│ Polling:     ✅ работает            │
└─────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 СТАТИСТИКА СЕССИИ
┌─────────────────────────────────────┐
│ 📥 Запросов сегодня:     {stats['requests_today']:<10} │
│ ✅ Успешных анализов:    {stats['successful']:<10} │
│ ❌ Ошибок:               {stats['errors']:<10} │
│ 📁 Файлов отправлено:    {stats['files_sent']:<10} │
└─────────────────────────────────────┘

⚙️ ВАША КОНФИГУРАЦИЯ
┌─────────────────────────────────────┐
│ ⚡ Quick Mode:      {quick_mode:<15} │
│ 🔔 Уведомления:    {notifications:<15} │
│ 🌐 Язык:           🇷🇺 Русский       │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 🟢 Все системы работают штатно     │
└─────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JARVIS v{VERSION} | BIMAR SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

def msg_my_tasks(user_id: int) -> str:
    tasks = get_completed_tasks(user_id)
    
    if not tasks:
        return f"""╔══════════════════════════════════════╗
║  📊 МОИ ЗАДАЧИ                      ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│                                     │
│         📭 ИСТОРИЯ ПУСТА            │
│                                     │
│   У вас пока нет завершенных        │
│   анализов.                         │
│                                     │
│   Нажмите «🚀 Новый анализ»         │
│   чтобы начать работу с JARVIS      │
│                                     │
└─────────────────────────────────────┘

💡 ПОДСКАЗКА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Для запуска первого анализа:
1. Нажмите «🚀 Новый анализ»
2. Отправьте URL сайта компании
3. Следуйте инструкциям JARVIS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JARVIS v{VERSION} | BIMAR SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
    
    task_lines = []
    for i, task in enumerate(tasks[:5], 1):
        domain = task.get("domain", "unknown")[:20]
        goal = task.get("goal", "")[:15]
        date = task.get("date", "")
        files_count = len(task.get("files", []))
        task_lines.append(f"""┌─────────────────────────────────────┐
│ #{i} ✅ ЗАВЕРШЕНО                     │
├─────────────────────────────────────┤
│ 🏢 {domain:<32} │
│ 🎯 {goal:<32} │
│ 📅 {date:<32} │
│ 📁 Документов: {files_count:<20} │
└─────────────────────────────────────┘""")
    
    tasks_text = "\n\n".join(task_lines)
    
    return f"""╔══════════════════════════════════════╗
║  📊 МОИ ЗАДАЧИ                      ║
╚══════════════════════════════════════╝

🗂️ Завершённые анализы (последние 5):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{tasks_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Для повторной загрузки документов
   нажмите кнопку с номером задачи.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JARVIS v{VERSION} | BIMAR SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

def msg_settings(user_id: int) -> str:
    settings = get_user_settings(user_id)
    quick_mode = "✅ ВКЛ" if settings.get("quick_mode") else "❌ ВЫКЛ"
    notifications = "✅ ВКЛ" if settings.get("notifications", True) else "❌ ВЫКЛ"
    default_goal = settings.get("default_goal") or "Не задана"
    
    return f"""╔══════════════════════════════════════╗
║  ⚙️ НАСТРОЙКИ JARVIS                ║
╚══════════════════════════════════════╝

Персональная конфигурация системы.
Выберите параметр для изменения.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────────────────┐
│ ⚡ QUICK MODE                       │
│ Текущий статус: {quick_mode:<18} │
│                                     │
│ Пропуск вопросов о цели встречи     │
│ и ограничениях клиента              │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 🔔 УВЕДОМЛЕНИЯ                      │
│ Текущий статус: {notifications:<18} │
│                                     │
│ Оповещения о статусе задач          │
│ и завершении анализа                │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 🌐 ЯЗЫК ИНТЕРФЕЙСА                  │
│ Текущий: 🇷🇺 Русский                │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 🎯 ЦЕЛЬ ПО УМОЛЧАНИЮ                │
│ Текущая: {default_goal:<26} │
└─────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JARVIS v{VERSION} | BIMAR SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

# Описания документов для гибридной выдачи
DOCUMENT_INFO = {
    "01_Досье_на_клиента": {
        "icon": "📋",
        "title": "Досье на клиента",
        "hint": "💡 Изучите перед встречей",
        "metrics": ["🏢 Профиль компании", "🎯 Точки входа", "👤 ЛПР выявлены", "⚠️ Ключевые боли"]
    },
    "02_Решения_BIMAR": {
        "icon": "🗺️",
        "title": "Решения BIMAR",
        "hint": "💡 Используйте на встрече",
        "metrics": ["📊 Сценарии использования", "⭐ Приоритетные", "🚀 Quick wins"]
    },
    "03_Экономика_сделки": {
        "icon": "💰",
        "title": "Экономика сделки",
        "hint": "💡 Ключевые цифры для переговоров",
        "metrics": ["💵 Экономия", "⏱️ Окупаемость", "📈 ROI"]
    },
    "04_Пилот_ТЗ": {
        "icon": "📝",
        "title": "Пилот ТЗ",
        "hint": "💡 Готово к согласованию",
        "metrics": ["🎯 Цели пилота", "📅 Длительность", "✅ KPI"]
    },
    "05_Лица_принимающие_решения": {
        "icon": "🎯",
        "title": "Лица принимающие решения",
        "hint": "💡 Стратегия работы внутри",
        "metrics": ["👤 Стейкхолдеры", "✅ ЛПР", "⚠️ Блокеры"]
    },
    "06_Питч_для_клиента": {
        "icon": "📊",
        "title": "Питч для клиента",
        "hint": "💡 Презентация для встречи",
        "metrics": ["📑 Слайдов: 10", "⏱️ Время: ~10 мин", "🎯 Экспресс-питч"]
    },
    "07_Верификация": {
        "icon": "📚",
        "title": "Верификация",
        "hint": "💡 Для проверки данных",
        "metrics": ["🔗 Источники", "📅 Дата сбора", "✅ Проверено"]
    }
}

def get_document_key(filename: str) -> str:
    """Извлекает ключ документа из имени файла"""
    for key in DOCUMENT_INFO.keys():
        if key in filename:
            return key
    return None

def msg_file_caption(filename: str) -> str:
    """Генерирует описание для файла в стиле JARVIS"""
    key = get_document_key(filename)
    if not key:
        return f"📎 {filename}"
    
    info = DOCUMENT_INFO[key]
    metrics_text = "\n".join([f"│ {m:<33} │" for m in info["metrics"]])
    
    return f"""{info['icon']} {info['title']}

┌─────────────────────────────────────┐
{metrics_text}
└─────────────────────────────────────┘

{info['hint']}"""

def msg_delivery_summary(domain: str, files_count: int, elapsed: str) -> str:
    """Генерирует компактное саммари перед выдачей файлов"""
    return f"""╔══════════════════════════════════════╗
║  📦 ПРЕСЕЙЛ-ПАКЕТ ГОТОВ             ║
║  {domain[:35]:<35} ║
╚══════════════════════════════════════╝

Сэр, миссия выполнена.
Доставляю {files_count} документов...

┌─ КЛЮЧЕВЫЕ МЕТРИКИ ──────────────────┐
│                                     │
│  📁 Документов:    {files_count:<16} │
│  ⏱️ Генерация:     {elapsed:<16} │
│  🎯 Клиент:        Проанализирован  │
│                                     │
└─────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

def msg_delivery_complete(domain: str, files_count: int, elapsed: str) -> str:
    """Генерирует финальное сообщение после выдачи всех файлов"""
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

╔══════════════════════════════════════╗
║  ✅ ДОСТАВКА ЗАВЕРШЕНА              ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│ 📁 Документов: {files_count:<20} │
│ ⏱️ Время генерации: {elapsed:<14} │
│ 🎯 Клиент: {domain[:24]:<24} │
└─────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Удачи на встрече, сэр.
🤖 JARVIS v{VERSION} | BIMAR SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

def msg_error(error_text: str) -> str:
    return f"""╔══════════════════════════════════════╗
║  ❌ ОШИБКА                          ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│ {error_text[:35]:<35} │
└─────────────────────────────────────┘

Попробуйте снова или обратитесь
в техническую поддержку BIMAR.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

def msg_access_denied() -> str:
    return """╔══════════════════════════════════════╗
║  🔒 ДОСТУП ЗАПРЕЩЕН                 ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│ У вас нет доступа к этой системе.   │
│                                     │
│ Обратитесь к администратору BIMAR   │
│ для получения доступа.              │
└─────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

# ═══════════════════════════════════════════════════════════════
# MANUS API
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# ПРОМПТ 1: ЭТАП 1 — АНАЛИЗ И ДОСЬЕ (только 1 документ)
# ═══════════════════════════════════════════════════════════════

async def create_manus_task_stage1(url: str, goal: str, constraints: str) -> Optional[str]:
    """Этап 1: Создаёт задачу для анализа компании и генерации ТОЛЬКО досье"""
    
    prompt = f"""═══════════════════════════════════════════════════════════════
JARVIS v3.0 — ЭТАП 1: АНАЛИЗ КОМПАНИИ И СОЗДАНИЕ ДОСЬЕ
═══════════════════════════════════════════════════════════════

РОЛЬ И ЦЕЛЬ
Ты — исследователь-аналитик для Коммерческого директора BimAR System.
Твоя задача: провести глубокий анализ компании-клиента и создать "deal-ready" досье,
чтобы понять бизнес, процессы и потенциал для применения решений BimAR.

ВХОДНЫЕ ДАННЫЕ
- URL сайта: {url}
- Цель встречи: {goal}
- Ограничения клиента: {constraints}

═══════════════════════════════════════════════════════════════
БАЗА ЗНАНИЙ BIMAR (используй для анализа потенциала)
═══════════════════════════════════════════════════════════════
В проекте BIMAR SYSTEM загружены файлы с информацией о продуктах и решениях:
- BIMAR_SYSTEM_Единая_база_знаний — полное описание модулей и возможностей
- BIMAR_Модульная_структура_продаж — структура продуктов для разных отраслей
- BIMAR-Логистика_Склад_Порт_СИЗ — решения для логистики и складов
- BIMAR-РФ — общая презентация компании
- Руководства пользователя — функционал приложений

ИСПОЛЬЗУЙ эти файлы для:
- Определения подходящих модулей BimAR для клиента
- Формирования гипотез о применении
- Оценки потенциала сделки

═══════════════════════════════════════════════════════════════
ОСНОВНОЙ ПРИНЦИП
═══════════════════════════════════════════════════════════════
Фокус на том, что помогает закрыть сделку: боли, процессы, ЛПР, потенциал для пилота.
Не пиши «энциклопедию» — только факты, которые приближают к пилоту и ТКП.

ИСТОЧНИКИ (обязательно цитировать с датой доступа)
1) Официальный сайт компании (о компании, контакты, проекты, услуги, новости, вакансии)
2) Закупки/тендеры: zakupki.gov.ru, коммерческие площадки
3) Отчётность/реестры: ЦБ/ФНС/ЕГРЮЛ, годовые отчёты
4) Косвенные источники: вакансии (для ИТ-ландшафта), техстатьи, презентации

Любое фактическое утверждение — со ссылкой.
Если данных нет — явно пометь как "ГИПОТЕЗА".

═══════════════════════════════════════════════════════════════
СТРУКТУРА ДОСЬЕ (01_Досье_на_клиента.docx)
═══════════════════════════════════════════════════════════════

1) EXECUTIVE SUMMARY (0.5 страницы)
   - Кто клиент: название, отрасль, география, масштаб (сотрудники/обороты)
   - Что делает: основной бизнес, продукты/услуги
   - Почему интересен для BimAR: 2-3 ключевые боли (с источниками)
   - Потенциал сделки: оценка (High/Med/Low) + краткое обоснование

2) ПОРТРЕТ КОМПАНИИ (0.5 страницы)
   - Основные площадки/филиалы
   - Карта процессов: где физические активы (склад/цех/стройка/эксплуатация)
   - ИТ-ландшафт (гипотезы): ERP/1C, WMS, CMMS/EAM, MES, GIS/BIM

3) ИНВЕНТАРЬ АКТИВОВ И БОЛЕЙ (0.5 страницы)
   Список активов по категориям (3-5 релевантных):
   - Склады/ЗИП/инструмент
   - Производство/ремонт/цеха
   - Стройка/капстрой
   - Полевая эксплуатация/бригады
   
   Для каждой боли: "как сейчас", "почему плохо", "как измерить"

4) ПОТЕНЦИАЛ ДЛЯ BimAR (0.5 страницы)
   - Топ-3 кейса применения BimAR (на основе базы знаний BIMAR)
   - Почему это деньги: какая метрика страдает
   - Рекомендуемая зона для пилота №1 (90 дней)

5) NEXT STEPS (0.25 страницы)
   - Какие данные запросить у клиента
   - Кого встретить (гипотезы по ЛПР)
   - Риски и барьеры

6) ИСТОЧНИКИ
   - Список всех источников с URL и датой доступа

═══════════════════════════════════════════════════════════════
ТРЕБОВАНИЯ К ОФОРМЛЕНИЮ
═══════════════════════════════════════════════════════════════
- Формат: DOCX (редактируемый, для мобильного просмотра)
- Объем: 2-3 страницы (не больше!)
- Язык: русский
- Все факты — со ссылками
- Гипотезы — помечены как "ГИПОТЕЗА"

═══════════════════════════════════════════════════════════════
ВАЖНО: СОЗДАЙ ТОЛЬКО ОДИН ДОКУМЕНТ
═══════════════════════════════════════════════════════════════
Создай ТОЛЬКО досье и сохрани как: 01_Досье_на_клиента.docx

НЕ создавай другие документы (презентации, таблицы, ТЗ).
Они будут созданы на следующем этапе по запросу пользователя.
"""

    headers = {
        "API_KEY": MANUS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"prompt": prompt, "projectId": MANUS_PROJECT_ID}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{MANUS_BASE_URL}/v1/tasks",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                data = await response.json()
                logger.info(f"Stage 1 task created: {data}")
                return data.get("task_id")
    except Exception as e:
        logger.error(f"Error creating stage 1 task: {e}")
        return None

# ═══════════════════════════════════════════════════════════════
# ПРОМПТ 2: ЭТАП 3 — ГЕНЕРАЦИЯ ВЫБРАННЫХ ДОКУМЕНТОВ
# ═══════════════════════════════════════════════════════════════

DOCUMENT_DESCRIPTIONS = {
    "solutions": """📊 02_Решения_BIMAR.xlsx
Карта модулей BimAR и сценариев применения для клиента.
Структура:
- Модуль BimAR | Сценарий | Боль клиента | Приоритет (1-3) | Сложность | Quick Win
- Минимум 10 сценариев, отсортированных по приоритету
- Выделить 3 Quick Wins для первой встречи""",
    
    "economics": """💰 03_Экономика_сделки.xlsx
ROI-калькулятор и экономическое обоснование.
Структура:
- Лист 1: Текущие потери (время, деньги, ресурсы)
- Лист 2: Экономия от внедрения BimAR (по сценариям)
- Лист 3: Стоимость пилота и полного внедрения
- Лист 4: ROI и срок окупаемости
Все цифры — обоснованные (источник или формула)""",
    
    "pilot": """📝 04_Пилот_ТЗ.docx
Техническое задание на пилотный проект (90 дней).
Структура:
- Цели и задачи пилота
- Scope: что входит / что НЕ входит
- KPI успеха (измеримые)
- Этапы и сроки
- Ресурсы (со стороны клиента и BimAR)
- Риски и митигация
- Критерии приёмки""",
    
    "stakeholders": """🎯 05_ЛПР_и_квалификация.xlsx
Stakeholder map и квалификация сделки по MEDDPICC.
Структура:
- Лист 1: Карта ЛПР (Имя | Должность | Роль | Влияние | Отношение | Стратегия)
- Лист 2: MEDDPICC (Metrics, Economic Buyer, Decision Criteria, Decision Process, Identify Pain, Champion, Competition)
- Лист 3: Next Steps (действие | ответственный | срок)""",
    
    "pitch": """📊 06_Питч_для_клиента.pptx
Презентация для встречи (10-12 слайдов).
Структура:
1. Титульный слайд
2. О компании клиента (показываем, что изучили)
3. Выявленные боли (3 ключевые)
4. Решение BimAR (как закрываем боли)
5-7. Сценарии применения (топ-3)
8. Экономический эффект (ROI)
9. Пилотный проект (scope, сроки, KPI)
10. Кейсы/референсы
11. Следующие шаги
12. Контакты""",
    
    "verification": """📚 07_Верификация.docx
Список источников и проверка данных.
Структура:
- Все использованные источники с URL и датой доступа
- Пометки: ✅ Подтверждено / ⚠️ Гипотеза / ❌ Не найдено
- Рекомендации по уточнению данных у клиента"""
}

async def create_manus_task_stage3(url: str, goal: str, constraints: str, selected_docs: list) -> Optional[str]:
    """Этап 3: Создаёт задачу для генерации ВЫБРАННЫХ документов"""
    
    # Формируем список выбранных документов с описаниями
    docs_list = []
    for doc_id in selected_docs:
        if doc_id in DOCUMENT_DESCRIPTIONS:
            docs_list.append(DOCUMENT_DESCRIPTIONS[doc_id])
    
    selected_docs_text = "\n\n".join(docs_list)
    
    prompt = f"""═══════════════════════════════════════════════════════════════
JARVIS v3.0 — ЭТАП 3: ГЕНЕРАЦИЯ ПРЕСЕЙЛ-ПАКЕТА
═══════════════════════════════════════════════════════════════

РОЛЬ И ЦЕЛЬ
Ты — исследователь-аналитик для Коммерческого директора BimAR System.
Твоя задача: на основе анализа компании создать "deal-ready" пакет материалов.

ВХОДНЫЕ ДАННЫЕ
- URL сайта: {url}
- Цель встречи: {goal}
- Ограничения клиента: {constraints}
- Досье клиента уже создано на Этапе 1 (используй информацию из анализа)

═══════════════════════════════════════════════════════════════
БАЗА ЗНАНИЙ BIMAR (ОБЯЗАТЕЛЬНО ИСПОЛЬЗОВАТЬ)
═══════════════════════════════════════════════════════════════
В проекте BIMAR SYSTEM загружены файлы — ИСПОЛЬЗУЙ ИХ:

📚 BIMAR_SYSTEM_Единая_база_знаний — полное описание модулей:
   - Модули: Склад, Производство, Стройка, Эксплуатация, Полевые работы
   - Функции: инвентаризация, навигация, AR-инструкции, цифровые двойники
   - Интеграции: 1C, SAP, Oracle, WMS, MES, CMMS

📊 BIMAR_Модульная_структура_продаж — что продаём:
   - Лицензии (по пользователям/объектам)
   - Внедрение (пилот 90 дней, полное внедрение)
   - Поддержка (SLA, обновления)

📋 Кейсы и референсы — используй для презентации:
   - Логистика: склады, порты, СИЗ
   - Производство: цеха, ремонт, ТОиР
   - Стройка: BIM, капстрой

ВАЖНО: Все данные о продуктах BimAR бери ТОЛЬКО из базы знаний проекта!

═══════════════════════════════════════════════════════════════
ДОКУМЕНТЫ ДЛЯ СОЗДАНИЯ (выбраны пользователем):
═══════════════════════════════════════════════════════════════

{selected_docs_text}

═══════════════════════════════════════════════════════════════
ТРЕБОВАНИЯ К ОФОРМЛЕНИЮ
═══════════════════════════════════════════════════════════════
- Форматы: .docx, .xlsx, .pptx (редактируемые, для мобильного просмотра)
- Язык: русский
- Профессиональный деловой стиль
- Все данные согласованы между документами
- Цифры и факты — только из базы знаний или помечены как гипотеза

═══════════════════════════════════════════════════════════════
ВАЖНО
═══════════════════════════════════════════════════════════════
- Создавай ТОЛЬКО указанные выше документы
- Используй информацию из досье клиента (Этап 1)
- Все данные о BimAR — из базы знаний проекта
- Фокус на закрытии сделки
"""

    headers = {
        "API_KEY": MANUS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"prompt": prompt, "projectId": MANUS_PROJECT_ID}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{MANUS_BASE_URL}/v1/tasks",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                data = await response.json()
                logger.info(f"Stage 3 task created: {data}")
                return data.get("task_id")
    except Exception as e:
        logger.error(f"Error creating stage 3 task: {e}")
        return None

# Для обратной совместимости — старая функция вызывает Этап 1
async def create_manus_task(url: str, goal: str, constraints: str) -> Optional[str]:
    """Обратная совместимость — вызывает Этап 1"""
    return await create_manus_task_stage1(url, goal, constraints)

async def get_task_status(task_id: str) -> Dict[str, Any]:
    headers = {"API_KEY": MANUS_API_KEY}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{MANUS_BASE_URL}/v1/tasks/{task_id}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                return await response.json()
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        return {"status": "error", "error": str(e)}

async def download_file(url: str, filename: str) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status == 200:
                    temp_dir = tempfile.mkdtemp()
                    filepath = os.path.join(temp_dir, filename)
                    with open(filepath, 'wb') as f:
                        f.write(await response.read())
                    return filepath
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
    return None

# ═══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ КОМАНД
# ═══════════════════════════════════════════════════════════════

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if not is_user_allowed(message.from_user.id):
        await message.answer(msg_access_denied())
        return
    await state.clear()
    await message.answer(msg_welcome(), reply_markup=get_main_keyboard())

@router.message(Command("help"))
async def cmd_help(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await message.answer(msg_help(), reply_markup=get_main_keyboard())

@router.message(Command("status"))
async def cmd_status(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await message.answer(msg_status(message.from_user.id), reply_markup=get_status_keyboard())

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Операция отменена.\n\nИспользуйте меню для навигации.", reply_markup=get_main_keyboard())

# ═══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ КНОПОК МЕНЮ
# ═══════════════════════════════════════════════════════════════

@router.message(F.text == "🚀 Новый анализ")
async def btn_new_analysis(message: Message, state: FSMContext):
    if not is_user_allowed(message.from_user.id):
        return
    stats["requests_today"] += 1
    await state.set_state(PresaleStates.waiting_for_url)
    await message.answer(msg_new_analysis(), reply_markup=get_cancel_keyboard())

@router.message(F.text == "📊 Мои задачи")
async def btn_my_tasks(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    user_id = message.from_user.id
    tasks = get_completed_tasks(user_id)
    if tasks:
        await message.answer(msg_my_tasks(user_id), reply_markup=get_tasks_keyboard(user_id))
    else:
        await message.answer(msg_my_tasks(user_id), reply_markup=get_main_keyboard())

@router.message(F.text == "⚙️ Настройки")
async def btn_settings(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await message.answer(msg_settings(message.from_user.id), reply_markup=get_settings_keyboard(message.from_user.id))

@router.message(F.text == "📈 Статус")
async def btn_status(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await message.answer(msg_status(message.from_user.id), reply_markup=get_status_keyboard())

@router.message(F.text == "📖 Справка")
async def btn_help(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await message.answer(msg_help(), reply_markup=get_main_keyboard())

# ═══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ CALLBACK
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Операция отменена.")
    await callback.message.answer("Используйте меню для навигации.", reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(F.data == "back_to_menu")
async def callback_back_to_menu(callback: CallbackQuery):
    await callback.message.edit_text("🏠 Главное меню")
    await callback.message.answer("Выберите действие:", reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(F.data == "back_to_settings")
async def callback_back_to_settings(callback: CallbackQuery):
    await callback.message.edit_text(msg_settings(callback.from_user.id), reply_markup=get_settings_keyboard(callback.from_user.id))
    await callback.answer()

@router.callback_query(F.data == "toggle_quick_mode")
async def callback_toggle_quick_mode(callback: CallbackQuery):
    settings = get_user_settings(callback.from_user.id)
    settings["quick_mode"] = not settings.get("quick_mode", False)
    status = "включен" if settings["quick_mode"] else "выключен"
    await callback.message.edit_text(msg_settings(callback.from_user.id), reply_markup=get_settings_keyboard(callback.from_user.id))
    await callback.answer(f"⚡ Quick Mode {status}")

@router.callback_query(F.data == "toggle_notifications")
async def callback_toggle_notifications(callback: CallbackQuery):
    settings = get_user_settings(callback.from_user.id)
    settings["notifications"] = not settings.get("notifications", True)
    status = "включены" if settings["notifications"] else "выключены"
    await callback.message.edit_text(msg_settings(callback.from_user.id), reply_markup=get_settings_keyboard(callback.from_user.id))
    await callback.answer(f"🔔 Уведомления {status}")

@router.callback_query(F.data == "settings_language")
async def callback_settings_language(callback: CallbackQuery):
    await callback.message.edit_text(
        """╔══════════════════════════════════════╗
║  🌐 ЯЗЫК ИНТЕРФЕЙСА                 ║
╚══════════════════════════════════════╝

Выберите язык системы JARVIS:

┌─────────────────────────────────────┐
│ 🇷🇺 Русский        ← ТЕКУЩИЙ       │
│ 🇬🇧 English                        │
└─────────────────────────────────────┘

💡 Язык влияет на:
• Интерфейс бота
• Генерируемые документы
• Системные сообщения""",
        reply_markup=get_language_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "settings_default_goal")
async def callback_settings_default_goal(callback: CallbackQuery):
    await callback.message.edit_text(
        """╔══════════════════════════════════════╗
║  🎯 ЦЕЛЬ ПО УМОЛЧАНИЮ               ║
╚══════════════════════════════════════╝

Выберите цель, которая будет
автоматически применяться к
новым анализам:

┌─────────────────────────────────────┐
│ ⭕ Не задана (спрашивать)           │
│ 🎯 Вводная/квалификация             │
│ 🚀 Согласование пилота              │
│ 💼 ТКП                              │
└─────────────────────────────────────┘""",
        reply_markup=get_default_goal_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("default_goal_"))
async def callback_set_default_goal(callback: CallbackQuery):
    goal_map = {
        "default_goal_none": None,
        "default_goal_intro": "Вводная/квалификация",
        "default_goal_pilot": "Согласование пилота",
        "default_goal_tkp": "ТКП"
    }
    settings = get_user_settings(callback.from_user.id)
    settings["default_goal"] = goal_map.get(callback.data)
    await callback.message.edit_text(msg_settings(callback.from_user.id), reply_markup=get_settings_keyboard(callback.from_user.id))
    await callback.answer("✅ Цель по умолчанию сохранена")

@router.callback_query(F.data.startswith("lang_"))
async def callback_set_language(callback: CallbackQuery):
    settings = get_user_settings(callback.from_user.id)
    settings["language"] = callback.data.replace("lang_", "")
    await callback.message.edit_text(msg_settings(callback.from_user.id), reply_markup=get_settings_keyboard(callback.from_user.id))
    await callback.answer("✅ Язык сохранен")

@router.callback_query(F.data == "refresh_status")
async def callback_refresh_status(callback: CallbackQuery):
    await callback.message.edit_text(
        """╔══════════════════════════════════════╗
║  📈 СТАТУС СИСТЕМЫ JARVIS           ║
╚══════════════════════════════════════╝

┌─────────────────────────────────────┐
│                                     │
│      🔄 ОБНОВЛЕНИЕ ДАННЫХ...        │
│                                     │
│      Сканирование систем...         │
│                                     │
└─────────────────────────────────────┘"""
    )
    await asyncio.sleep(1)
    await callback.message.edit_text(msg_status(callback.from_user.id), reply_markup=get_status_keyboard())
    await callback.answer("✅ Статус обновлен")

@router.callback_query(F.data.startswith("goal_"))
async def callback_select_goal(callback: CallbackQuery, state: FSMContext):
    goal_map = {
        "goal_intro": "Вводная/квалификация",
        "goal_pilot": "Согласование пилота",
        "goal_tkp": "ТКП"
    }
    goal = goal_map.get(callback.data, "ТКП")
    await state.update_data(goal=goal)
    await callback.message.edit_text("✅ Цель: " + goal)
    await callback.answer()
    
    # Запускаем процесс генерации пресейл-пакета
    await process_presale(callback.message, state, callback.from_user.id)

# ═══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ СОСТОЯНИЙ
# ═══════════════════════════════════════════════════════════════

@router.message(StateFilter(PresaleStates.waiting_for_url))
async def handle_url(message: Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    if not validate_url(url):
        await message.answer(msg_error("Неверный формат URL"), reply_markup=get_cancel_keyboard())
        return
    
    domain = urlparse(url).netloc
    await state.update_data(url=url, domain=domain)
    settings = get_user_settings(message.from_user.id)
    
    if settings.get("quick_mode") and settings.get("default_goal"):
        await state.update_data(goal=settings["default_goal"], constraints="-")
        await message.answer(f"✅ URL: {domain}\n✅ Цель: {settings['default_goal']}")
        await process_presale(message, state, message.from_user.id)
    else:
        await state.set_state(PresaleStates.waiting_for_goal)
        await message.answer(msg_url_accepted(domain), reply_markup=get_goals_keyboard())

@router.message(StateFilter(PresaleStates.waiting_for_constraints))
async def handle_constraints(message: Message, state: FSMContext):
    constraints = message.text.strip()
    await state.update_data(constraints=constraints)
    await process_presale(message, state, message.from_user.id)

# ═══════════════════════════════════════════════════════════════
# ОСНОВНАЯ ЛОГИКА ПРЕСЕЙЛА
# ═══════════════════════════════════════════════════════════════

async def process_presale(message: Message, state: FSMContext, user_id: int):
    data = await state.get_data()
    url = data.get("url")
    domain = data.get("domain")
    goal = data.get("goal")
    constraints = data.get("constraints", "-")
    
    await state.set_state(PresaleStates.processing)
    status_msg = await message.answer(msg_processing_start())
    start_time = datetime.now()
    
    task_id = await create_manus_task(url, goal, constraints)
    
    if not task_id:
        stats["errors"] += 1
        add_user_task(user_id, {"domain": domain, "goal": goal, "status": "error", "date": datetime.now().strftime("%d.%m.%Y %H:%M")})
        await status_msg.edit_text(msg_error("Не удалось создать задачу в Manus"))
        await state.clear()
        await message.answer("Используйте меню для повторной попытки.", reply_markup=get_main_keyboard())
        return
    
    task_info = {"task_id": task_id, "domain": domain, "goal": goal, "status": "running", "date": datetime.now().strftime("%d.%m.%Y %H:%M")}
    add_user_task(user_id, task_info)
    
    iteration = 0
    stages = ["Анализ компании", "Сбор данных", "Генерация документов", "Финализация"]
    
    while True:
        elapsed = datetime.now() - start_time
        elapsed_sec = int(elapsed.total_seconds())
        elapsed_min = elapsed_sec // 60
        elapsed_sec_display = elapsed_sec % 60
        
        if elapsed_sec > TASK_TIMEOUT:
            stats["errors"] += 1
            task_info["status"] = "error"
            await status_msg.edit_text(msg_error("Превышено время ожидания"))
            await state.clear()
            await message.answer("Используйте меню для повторной попытки.", reply_markup=get_main_keyboard())
            return
        
        task_status = await get_task_status(task_id)
        status = task_status.get("status", "running")
        
        if status == "completed":
            break
        elif status == "failed":
            stats["errors"] += 1
            task_info["status"] = "error"
            await status_msg.edit_text(msg_error("Задача завершилась с ошибкой"))
            await state.clear()
            await message.answer("Используйте меню для повторной попытки.", reply_markup=get_main_keyboard())
            return
        
        iteration += 1
        stage_idx = min(iteration // 10, len(stages) - 1)
        percent = min(iteration * 3, 95)
        
        try:
            await status_msg.edit_text(msg_processing_progress(elapsed_min, elapsed_sec_display, stages[stage_idx], percent))
        except:
            pass
        
        await asyncio.sleep(POLLING_INTERVAL)
    
    task_info["status"] = "completed"
    stats["successful"] += 1
    
    # Извлекаем файлы (должен быть только 1 файл — досье)
    artifacts = []
    for output_item in task_status.get("output", []):
        content = output_item.get("content", [])
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "output_file" and item.get("fileUrl"):
                    artifacts.append({
                        "url": item.get("fileUrl"),
                        "name": item.get("fileName", "file")
                    })
    
    logger.info(f"Stage 1 completed: {len(artifacts)} files")
    
    # Вычисляем время генерации
    elapsed = datetime.now() - start_time
    elapsed_str = f"{int(elapsed.total_seconds()) // 60:02d}:{int(elapsed.total_seconds()) % 60:02d}"
    
    await status_msg.edit_text(f"✅ Анализ завершён ({elapsed_str})")
    
    # Отправляем досье
    for artifact in artifacts:
        file_url = artifact.get("url")
        file_name = artifact.get("name", "file")
        
        if file_url:
            filepath = await download_file(file_url, file_name)
            if filepath:
                try:
                    caption = msg_file_caption(file_name)
                    await message.answer_document(FSInputFile(filepath, filename=file_name), caption=caption)
                    stats["files_sent"] += 1
                except Exception as e:
                    logger.error(f"Error sending file: {e}")
                finally:
                    try:
                        os.remove(filepath)
                    except:
                        pass
    
    # Показываем меню выбора документов (ЭТАП 2)
    await state.set_state(PresaleStates.selecting_docs)
    await message.answer(
        f"""✅ Досье на {domain} готово!

📊 Выберите документы для генерации:

Отметьте нужные документы и нажмите "Создать выбранные".""",
        reply_markup=get_document_selector_keyboard(set())
    )

# ═══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ ВЫБОРА ДОКУМЕНТОВ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("toggle_doc_"))
async def callback_toggle_doc(callback: CallbackQuery, state: FSMContext):
    """Переключение выбора одного документа"""
    doc_id = callback.data.replace("toggle_doc_", "")
    data = await state.get_data()
    selected = set(data.get("selected_docs", []))
    
    if doc_id in selected:
        selected.remove(doc_id)
    else:
        selected.add(doc_id)
    
    await state.update_data(selected_docs=list(selected))
    await callback.message.edit_reply_markup(reply_markup=get_document_selector_keyboard(selected))
    await callback.answer()

@router.callback_query(F.data == "toggle_all_docs")
async def callback_toggle_all(callback: CallbackQuery, state: FSMContext):
    """Выбрать/снять все документы"""
    data = await state.get_data()
    selected = set(data.get("selected_docs", []))
    
    if len(selected) == len(SELECTABLE_DOCS):
        selected = set()  # Снять все
    else:
        selected = set(SELECTABLE_DOCS)  # Выбрать все
    
    await state.update_data(selected_docs=list(selected))
    await callback.message.edit_reply_markup(reply_markup=get_document_selector_keyboard(selected))
    await callback.answer()

@router.callback_query(F.data == "confirm_docs")
async def callback_confirm_docs(callback: CallbackQuery, state: FSMContext):
    """Подтверждение выбора и запуск генерации"""
    data = await state.get_data()
    selected = data.get("selected_docs", [])
    
    if not selected:
        await callback.answer("⚠️ Выберите хотя бы 1 документ", show_alert=True)
        return
    
    summary = get_selected_docs_summary(set(selected))
    await callback.message.edit_text(f"""✅ Выбрано {len(selected)} документов:

{summary}

⏳ Запускаю генерацию...""")
    await callback.answer()
    
    # Запускаем ЭТАП 3: Генерация выбранных документов
    await state.set_state(PresaleStates.generating_docs)
    await process_selected_documents(callback.message, state, callback.from_user.id)

async def process_selected_documents(message: Message, state: FSMContext, user_id: int):
    """ЭТАП 3: Генерация выбранных документов"""
    data = await state.get_data()
    url = data.get("url")
    domain = data.get("domain")
    goal = data.get("goal")
    constraints = data.get("constraints", "-")
    selected_docs = data.get("selected_docs", [])
    
    status_msg = await message.answer(msg_processing_start())
    start_time = datetime.now()
    
    # Создаём задачу для генерации выбранных документов
    task_id = await create_manus_task_stage3(url, goal, constraints, selected_docs)
    
    if not task_id:
        stats["errors"] += 1
        await status_msg.edit_text(msg_error("Не удалось создать задачу в Manus"))
        await state.clear()
        await message.answer("Используйте меню для повторной попытки.", reply_markup=get_main_keyboard())
        return
    
    iteration = 0
    stages = ["Генерация документов", "Формирование пакета", "Финализация"]
    
    while True:
        elapsed = datetime.now() - start_time
        elapsed_sec = int(elapsed.total_seconds())
        elapsed_min = elapsed_sec // 60
        elapsed_sec_display = elapsed_sec % 60
        
        if elapsed_sec > TASK_TIMEOUT:
            stats["errors"] += 1
            await status_msg.edit_text(msg_error("Превышено время ожидания"))
            await state.clear()
            await message.answer("Используйте меню для повторной попытки.", reply_markup=get_main_keyboard())
            return
        
        task_status = await get_task_status(task_id)
        status = task_status.get("status", "running")
        
        if status == "completed":
            break
        elif status == "failed":
            stats["errors"] += 1
            await status_msg.edit_text(msg_error("Задача завершилась с ошибкой"))
            await state.clear()
            await message.answer("Используйте меню для повторной попытки.", reply_markup=get_main_keyboard())
            return
        
        iteration += 1
        stage_idx = min(iteration // 10, len(stages) - 1)
        percent = min(iteration * 3, 95)
        
        try:
            await status_msg.edit_text(msg_processing_progress(elapsed_min, elapsed_sec_display, stages[stage_idx], percent))
        except:
            pass
        
        await asyncio.sleep(POLLING_INTERVAL)
    
    stats["successful"] += 1
    
    # Извлекаем файлы
    artifacts = []
    for output_item in task_status.get("output", []):
        content = output_item.get("content", [])
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "output_file" and item.get("fileUrl"):
                    artifacts.append({
                        "url": item.get("fileUrl"),
                        "name": item.get("fileName", "file")
                    })
    
    logger.info(f"Found {len(artifacts)} files to send")
    files_sent = 0
    
    elapsed = datetime.now() - start_time
    elapsed_str = f"{int(elapsed.total_seconds()) // 60:02d}:{int(elapsed.total_seconds()) % 60:02d}"
    
    await status_msg.edit_text(msg_delivery_summary(domain, len(artifacts), elapsed_str))
    
    # Отправляем файлы
    for artifact in artifacts:
        file_url = artifact.get("url")
        file_name = artifact.get("name", "file")
        
        if file_url:
            filepath = await download_file(file_url, file_name)
            if filepath:
                try:
                    caption = msg_file_caption(file_name)
                    await message.answer_document(FSInputFile(filepath, filename=file_name), caption=caption)
                    files_sent += 1
                    stats["files_sent"] += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Error sending file: {e}")
                finally:
                    try:
                        os.remove(filepath)
                    except:
                        pass
    
    await message.answer(msg_delivery_complete(domain, files_sent, elapsed_str), reply_markup=get_main_keyboard())
    await state.clear()

@router.callback_query(F.data == "noop")
async def callback_noop(callback: CallbackQuery):
    """Пустой callback для неактивных кнопок"""
    await callback.answer()

# ═══════════════════════════════════════════════════════════════
# ЗАПУСК БОТА
# ═══════════════════════════════════════════════════════════════

async def main():
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  🤖 JARVIS v{VERSION} - BIMAR Presale Intelligence System       ║
╚══════════════════════════════════════════════════════════════╝
    """)
    print(f"Manus API URL: {MANUS_BASE_URL}")
    print(f"Project ID: {MANUS_PROJECT_ID}")
    print(f"Quick Mode (default): {QUICK_MODE_DEFAULT}")
    print(f"Allowed users: {'All' if not ALLOWED_USER_IDS else ALLOWED_USER_IDS}")
    print("=" * 60)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
