# Типы документов для выбора
# Форматы оптимизированы для:
# - Редактирования (Google Docs/Sheets/Slides, MS Office)
# - Просмотра на iPhone/Android

DOCUMENT_TYPES = {
    "dossier": {
        "id": "dossier",
        "name": "01_Досье_на_клиента",
        "filename": "01_Досье_на_клиента.docx",
        "format": "docx",
        "icon": "📋",
        "description": "Профиль компании, боли, ЛПР",
        "mobile_view": "Google Docs / MS Word",
        "mandatory": True  # Всегда генерируется на Этапе 1
    },
    "use_cases": {
        "id": "use_cases",
        "name": "02_Решения_BIMAR",
        "filename": "02_Решения_BIMAR.xlsx",
        "format": "xlsx",
        "icon": "🗺️",
        "description": "Карта модулей BimAR и сценариев",
        "mobile_view": "Google Sheets / MS Excel"
    },
    "roi": {
        "id": "roi",
        "name": "03_Экономика_сделки",
        "filename": "03_Экономика_сделки.xlsx",
        "format": "xlsx",
        "icon": "💰",
        "description": "ROI калькулятор + стоимость пилота",
        "mobile_view": "Google Sheets / MS Excel"
    },
    "sow": {
        "id": "sow",
        "name": "04_Пилот_ТЗ",
        "filename": "04_Пилот_ТЗ.docx",
        "format": "docx",
        "icon": "📝",
        "description": "Техзадание на пилот 90 дней",
        "mobile_view": "Google Docs / MS Word"
    },
    "stakeholders": {
        "id": "stakeholders",
        "name": "05_ЛПР_и_квалификация",
        "filename": "05_ЛПР_и_квалификация.xlsx",
        "format": "xlsx",
        "icon": "🎯",
        "description": "Карта ЛПР + MEDDPICC",
        "mobile_view": "Google Sheets / MS Excel"
    },
    "presentation": {
        "id": "presentation",
        "name": "06_Питч_для_клиента",
        "filename": "06_Питч_для_клиента.pptx",
        "format": "pptx",
        "icon": "📊",
        "description": "Презентация 10-12 слайдов",
        "mobile_view": "Google Slides / MS PowerPoint"
    },
    "verification": {
        "id": "verification",
        "name": "07_Верификация",
        "filename": "07_Верификация.docx",
        "format": "docx",
        "icon": "✅",
        "description": "Чек-лист готовности пресейла",
        "mobile_view": "Google Docs / MS Word"
    }
}

# Список документов для выбора (исключая обязательные)
SELECTABLE_DOCS = [k for k, v in DOCUMENT_TYPES.items() if not v.get("mandatory", False)]

# Форматы файлов для мобильной совместимости
FILE_FORMATS = {
    "docx": {
        "name": "Microsoft Word",
        "mobile_apps": ["Google Docs", "Microsoft Word", "WPS Office"],
        "editable": True,
        "ios_native": True,
        "android_native": True
    },
    "xlsx": {
        "name": "Microsoft Excel",
        "mobile_apps": ["Google Sheets", "Microsoft Excel", "WPS Office"],
        "editable": True,
        "ios_native": True,
        "android_native": True
    },
    "pptx": {
        "name": "Microsoft PowerPoint",
        "mobile_apps": ["Google Slides", "Microsoft PowerPoint", "WPS Office"],
        "editable": True,
        "ios_native": True,
        "android_native": True
    }
}

# Примечание для пользователей
MOBILE_NOTE = """
📱 Все документы в редактируемых форматах:
• .docx — открывается в Google Docs / Word
• .xlsx — открывается в Google Sheets / Excel  
• .pptx — открывается в Google Slides / PowerPoint

Для просмотра на iPhone/Android:
1. Скачайте файл
2. Откройте в Google Drive или Microsoft Office
3. Редактируйте прямо на телефоне!
"""
