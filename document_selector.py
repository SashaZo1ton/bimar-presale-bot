# Клавиатура для выбора документов

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from document_types import DOCUMENT_TYPES, SELECTABLE_DOCS

def get_document_selector_keyboard(selected_docs=None):
    """
    Создаёт клавиатуру с toggle-кнопками для выбора документов
    selected_docs: set() — уже выбранные документы
    """
    if selected_docs is None:
        selected_docs = set()
    
    buttons = []
    
    # Кнопки для каждого документа
    for doc_id in SELECTABLE_DOCS:
        doc = DOCUMENT_TYPES[doc_id]
        is_selected = doc_id in selected_docs
        
        # Иконка + галочка если выбрано
        icon = doc["icon"]
        check = "✅ " if is_selected else ""
        text = f"{check}{icon} {doc['description']}"
        
        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"toggle_doc_{doc_id}"
        )])
    
    # Кнопка "Выбрать всё" / "Снять всё"
    all_selected = len(selected_docs) == len(SELECTABLE_DOCS)
    select_all_text = "❌ Снять всё" if all_selected else "✅ Выбрать всё"
    buttons.append([InlineKeyboardButton(
        text=select_all_text,
        callback_data="toggle_all_docs"
    )])
    
    # Кнопка "Готово" (активна только если что-то выбрано)
    if selected_docs:
        buttons.append([InlineKeyboardButton(
            text=f"🚀 Генерировать ({len(selected_docs)} док.)",
            callback_data="confirm_docs"
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text="⚠️ Выберите хотя бы 1 документ",
            callback_data="noop"
        )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_selected_docs_summary(selected_docs):
    """
    Возвращает текстовое описание выбранных документов
    """
    if not selected_docs:
        return "Не выбрано ни одного документа"
    
    lines = []
    for doc_id in selected_docs:
        doc = DOCUMENT_TYPES[doc_id]
        lines.append(f"{doc['icon']} {doc['name']}")
    
    return "\n".join(lines)
