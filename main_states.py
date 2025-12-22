"""
FSM состояния для JARVIS бота
Вынесены в отдельный файл для избежания циклических импортов
"""
from aiogram.fsm.state import State, StatesGroup

class PresaleStates(StatesGroup):
    waiting_url = State()
    waiting_goal = State()
    analyzing = State()  # Этап 1: Анализ и генерация досье
    selecting_docs = State()  # Этап 2: Выбор документов
    generating_docs = State()  # Этап 3: Генерация выбранных документов
