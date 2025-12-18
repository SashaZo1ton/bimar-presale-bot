# Быстрый старт BIMAR Presale Bot

## За 5 минут до первого запуска

### 1. Получите необходимые ключи

**Telegram Bot Token:**
- Откройте Telegram и найдите [@BotFather](https://t.me/botfather)
- Выполните команду `/newbot`
- Следуйте инструкциям
- Скопируйте токен (выглядит как `123456:ABC-DEF...`)

**Manus API Key:**
- Перейдите на https://app.manus.ai
- Откройте Settings → API Keys
- Создайте новый ключ
- Скопируйте значение

**Manus Project ID:**
- На https://app.manus.ai откройте ваш Project
- Скопируйте ID из URL или Settings

### 2. Установите зависимости

```bash
# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate

# Установите зависимости
pip install -r requirements.txt
```

### 3. Создайте .env файл

```bash
cp .env.example .env
```

Отредактируйте `.env` и вставьте ваши ключи:

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
MANUS_API_KEY=sk-your-api-key-here
MANUS_PROJECT_ID=YghG6cpo3udE8p2gcYzQfP
ALLOWED_USER_IDS=your_telegram_user_id
QUICK_MODE=0
```

### 4. Запустите бота

```bash
python bot.py
```

Вы должны увидеть:
```
2024-01-15 10:30:45,123 - __main__ - INFO - Starting BIMAR Presale Bot...
2024-01-15 10:30:46,456 - __main__ - INFO - Manus API URL: https://api.manus.ai
```

### 5. Тестируйте в Telegram

1. Найдите вашего бота в Telegram (по имени, которое вы дали BotFather)
2. Отправьте `/start`
3. Отправьте URL компании (например: `https://google.com`)
4. Следуйте инструкциям бота

## Получение вашего Telegram User ID

Если вы не знаете ваш User ID:

1. Отправьте любое сообщение боту
2. Посмотрите логи бота - там будет ваш ID
3. Или используйте [@userinfobot](https://t.me/userinfobot) в Telegram

## Быстрый режим (QUICK_MODE)

Если вы хотите, чтобы бот не задавал вопросы:

```env
QUICK_MODE=1
```

Тогда бот будет использовать значения по умолчанию:
- Цель встречи: "вводная/квалификация"
- Ограничения: "неизвестно"

## Ограничение доступа

Чтобы разрешить доступ только определенным пользователям:

```env
ALLOWED_USER_IDS=123456789,987654321,555666777
```

Если строка пуста - доступ открыт для всех.

## Docker (альтернатива)

Если у вас установлен Docker:

```bash
docker-compose up -d
```

Бот будет работать в фоне.

## Решение проблем

### "ModuleNotFoundError: No module named 'aiogram'"

```bash
pip install -r requirements.txt
```

### "TELEGRAM_BOT_TOKEN not set"

1. Убедитесь, что файл `.env` существует
2. Проверьте, что переменная установлена: `echo $TELEGRAM_BOT_TOKEN`
3. Перезагрузите окружение: `source venv/bin/activate`

### Бот не отвечает в Telegram

1. Убедитесь, что бот запущен: `ps aux | grep bot.py`
2. Проверьте логи для ошибок
3. Убедитесь, что токен корректен

## Следующие шаги

- Прочитайте полную документацию в [README.md](README.md)
- Изучите конфигурацию в [.env.example](.env.example)
- Проверьте логирование для отладки
