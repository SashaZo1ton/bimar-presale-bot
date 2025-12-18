# BIMAR Presale Bot

Telegram-бот для автоматической генерации пресейл-пакетов компаний через Manus API.

## Описание

Бот принимает URL компании, создает задачу в Manus Project (с KB + master prompt для пресейла) и возвращает в Telegram 7 артефактов:

- **Deal_Brief.pdf** - краткое описание сделки
- **Use_Case_Map.xlsx** - карта use case'ов
- **ROI_Calc.xlsx** - расчет ROI
- **Pilot_SOW.docx** - SOW для пилота
- **MAP.xlsx** - матрица анализа проблем
- **Mini_Deck.pptx** - мини-презентация
- **Sources.md** - источники и ссылки

## Требования

- Python 3.8+
- Telegram Bot Token (получить у [@BotFather](https://t.me/botfather))
- Manus API Key (получить в [личном кабинете Manus](https://app.manus.ai))
- Manus Project ID (ID вашего проекта с KB + master prompt)

## Установка

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd bimar_presale_bot
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Конфигурация переменных окружения

Скопируйте `.env.example` в `.env` и заполните значения:

```bash
cp .env.example .env
```

Отредактируйте `.env`:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
MANUS_API_KEY=your_manus_api_key_here
MANUS_BASE_URL=https://api.manus.ai
MANUS_PROJECT_ID=your_project_id_here
ALLOWED_USER_IDS=123456789,987654321
QUICK_MODE=0
```

## Запуск

### Локально

```bash
python bot.py
```

Бот будет работать в режиме polling и слушать сообщения от пользователей.

### В Docker

```bash
docker-compose up -d
```

Или вручную:

```bash
docker build -t bimar-presale-bot .
docker run -d --env-file .env bimar-presale-bot
```

## Использование

### Для пользователя

1. Найдите бота в Telegram и нажмите `/start`
2. Отправьте URL компании (например: `https://example.com`)
3. Выберите цель встречи (если `QUICK_MODE=0`):
   - Вводная/квалификация
   - Согласование пилота
   - ТКП
4. Укажите ограничения (если `QUICK_MODE=0`):
   - on-prem, ИБ, камера, без облака и т.д.
   - Или отправьте `-` если ограничений нет
5. Ожидайте результатов (обычно 5-25 минут)
6. Получите пресейл-пакет (7 файлов)

### Команды бота

- `/start` - Начать работу
- `/help` - Справка
- `/cancel` - Отменить текущую операцию

## Конфигурация

### Обязательные переменные

| Переменная | Описание | Пример |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token от BotFather | `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` |
| `MANUS_API_KEY` | API Key для Manus | `sk-...` |
| `MANUS_PROJECT_ID` | ID вашего Manus Project | `YghG6cpo3udE8p2gcYzQfP` |

### Опциональные переменные

| Переменная | Описание | По умолчанию |
|---|---|---|
| `MANUS_BASE_URL` | URL API Manus | `https://api.manus.ai` |
| `ALLOWED_USER_IDS` | Список ID пользователей (через запятую) | Все пользователи |
| `QUICK_MODE` | Быстрый режим без вопросов (1/0) | `0` |
| `TASK_TIMEOUT` | Таймаут ожидания результата (сек) | `1500` (25 минут) |
| `POLLING_INTERVAL` | Интервал проверки статуса (сек) | `10` |

## Ограничение доступа

Для ограничения доступа только определенным пользователям используйте `ALLOWED_USER_IDS`:

```env
ALLOWED_USER_IDS=123456789,987654321,555666777
```

Если переменная не установлена, доступ открыт для всех.

## Режимы работы

### QUICK_MODE=0 (по умолчанию)

Бот задает вопросы пользователю:
1. Цель встречи (выбор из 3 вариантов)
2. Ограничения (текстовый ввод)

### QUICK_MODE=1

Бот не задает вопросы, использует значения по умолчанию:
- Цель встречи: "вводная/квалификация"
- Ограничения: "неизвестно"

## Тестирование

### Локальное тестирование

1. Запустите бота:
   ```bash
   python bot.py
   ```

2. В Telegram найдите вашего бота и отправьте `/start`

3. Отправьте URL компании (например: `https://google.com`)

4. Следуйте инструкциям бота

5. Проверьте логи в консоли:
   ```
   2024-01-15 10:30:45,123 - __main__ - INFO - Task created: task_123456
   2024-01-15 10:30:50,456 - __main__ - INFO - Task task_123456 status: processing
   ```

### Проверка конфигурации

Перед запуском убедитесь, что все переменные окружения установлены:

```bash
echo $TELEGRAM_BOT_TOKEN
echo $MANUS_API_KEY
echo $MANUS_PROJECT_ID
```

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                      Telegram User                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    BIMAR Presale Bot                        │
│  (aiogram, FSM, polling)                                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Manus API Client                         │
│  POST /v1/tasks (create)                                    │
│  GET /v1/tasks/{id} (poll)                                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      Manus API                              │
│  (Project with KB + master prompt)                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Presale Artifacts                         │
│  (PDF, XLSX, DOCX, PPTX, MD)                               │
└─────────────────────────────────────────────────────────────┘
```

## Логирование

Бот логирует все операции в консоль:

```
2024-01-15 10:30:45,123 - __main__ - INFO - Starting BIMAR Presale Bot...
2024-01-15 10:30:46,456 - __main__ - INFO - Manus API URL: https://api.manus.ai
2024-01-15 10:30:47,789 - __main__ - INFO - Project ID: YghG6cpo3udE8p2gcYzQfP
2024-01-15 10:30:48,012 - __main__ - INFO - Task created: task_123456
```

Для более детального логирования измените уровень в `bot.py`:

```python
logging.basicConfig(level=logging.DEBUG)
```

## Обработка ошибок

Бот обрабатывает следующие ошибки:

- **Неверный URL** - Пользователю предлагается отправить корректный URL
- **Таймаут задачи** - Задача не завершилась за 25 минут
- **Ошибка Manus API** - Задача завершилась с ошибкой
- **Отсутствующие файлы** - Бот отправляет имеющиеся файлы и сообщает об отсутствующих
- **Ошибка загрузки файла** - Бот повторяет попытку до 3 раз

## Структура проекта

```
bimar_presale_bot/
├── bot.py                 # Основной код бота
├── requirements.txt       # Зависимости Python
├── .env.example          # Пример переменных окружения
├── .env                  # Переменные окружения (не коммитить!)
├── Dockerfile            # Docker конфигурация
├── docker-compose.yml    # Docker Compose конфигурация
├── README.md             # Этот файл
└── downloads/            # Папка для скачанных файлов (создается автоматически)
```

## Развертывание

### На VPS/сервере

1. Установите Python 3.8+
2. Клонируйте репозиторий
3. Установите зависимости: `pip install -r requirements.txt`
4. Создайте `.env` с конфигурацией
5. Запустите бота: `python bot.py`

Для автоматического перезапуска используйте systemd или supervisor.

### На Heroku

1. Создайте `Procfile`:
   ```
   worker: python bot.py
   ```

2. Установите Heroku CLI и разверните:
   ```bash
   heroku create your-app-name
   heroku config:set TELEGRAM_BOT_TOKEN=...
   heroku config:set MANUS_API_KEY=...
   heroku config:set MANUS_PROJECT_ID=...
   git push heroku main
   ```

## Решение проблем

### Бот не отвечает

1. Проверьте, что `TELEGRAM_BOT_TOKEN` корректен
2. Убедитесь, что бот запущен: `ps aux | grep bot.py`
3. Проверьте логи для ошибок

### Ошибка "MANUS_API_KEY not set"

1. Убедитесь, что файл `.env` существует
2. Проверьте, что переменная установлена: `echo $MANUS_API_KEY`
3. Перезагрузите окружение: `source venv/bin/activate`

### Задача не завершается

1. Проверьте, что `MANUS_PROJECT_ID` корректен
2. Убедитесь, что в проекте есть master prompt
3. Увеличьте `TASK_TIMEOUT` в `.env`

### Файлы не скачиваются

1. Проверьте интернет соединение
2. Убедитесь, что `fileUrl` в ответе Manus API доступен
3. Проверьте права на запись в папку `downloads/`

## Поддержка

Для вопросов и проблем:

1. Проверьте логи бота
2. Убедитесь, что все переменные окружения установлены
3. Проверьте документацию Manus API: https://open.manus.im/docs
4. Проверьте документацию aiogram: https://docs.aiogram.dev

## Лицензия

MIT License

## Автор

BIMAR Team
