# Этап 1: Анализ компании и генерация досье

async def process_analysis(message, state, user_id):
    """
    Этап 1: Анализ компании и генерация только досье + источники
    """
    from bot import (
        msg_processing_start, msg_error, get_main_keyboard,
        create_manus_task, get_task_status, extract_files_from_response,
        download_file, stats, add_user_task, TASK_TIMEOUT, POLLING_INTERVAL,
        PresaleStates, get_document_selector_keyboard
    )
    from datetime import datetime
    import asyncio
    
    data = await state.get_data()
    url = data.get("url")
    domain = data.get("domain")
    goal = data.get("goal")
    
    status_msg = await message.answer(f"""╔══════════════════════════════════════╗
║  🔍 ЭТАП 1: АНАЛИЗ КОМПАНИИ         ║
╚══════════════════════════════════════╝

⏳ Анализирую {domain}...

💡 JARVIS изучает компанию и готовит досье.
   Это займёт 5-10 минут.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JARVIS v3.0 | BIMAR SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")
    
    start_time = datetime.now()
    
    # Промпт для генерации только досье
    analysis_prompt = f"""Проанализируй компанию по URL: {url}
    
Цель встречи: {goal}

Сгенерируй ТОЛЬКО 2 документа:
1. 01_Досье_на_клиента.pdf — полный профиль компании
2. 07_Верификация.md — список источников

Досье должно содержать:
- Общая информация о компании
- Отрасль и направления бизнеса
- Ключевые лица (ЛПР, ЛВР)
- Текущие боли и вызовы
- Потенциальные точки входа для BIMAR
- Новости за последний год"""
    
    task_id = await create_manus_task(url, goal, analysis_prompt, doc_type="analysis")
    
    if not task_id:
        stats["errors"] += 1
        await status_msg.edit_text(msg_error("Не удалось создать задачу анализа"))
        await state.clear()
        await message.answer("Используйте меню для повторной попытки.", reply_markup=get_main_keyboard())
        return
    
    # Ждём завершения анализа
    iteration = 0
    while True:
        elapsed = datetime.now() - start_time
        elapsed_sec = int(elapsed.total_seconds())
        
        if elapsed_sec > TASK_TIMEOUT:
            stats["errors"] += 1
            await status_msg.edit_text(msg_error("Превышено время ожидания анализа"))
            await state.clear()
            await message.answer("Используйте меню для повторной попытки.", reply_markup=get_main_keyboard())
            return
        
        task_status = await get_task_status(task_id)
        status = task_status.get("status", "running")
        
        if status == "completed":
            break
        elif status == "failed":
            stats["errors"] += 1
            await status_msg.edit_text(msg_error("Анализ завершился с ошибкой"))
            await state.clear()
            await message.answer("Используйте меню для повторной попытки.", reply_markup=get_main_keyboard())
            return
        
        # Обновляем прогресс
        iteration += 1
        if iteration % 3 == 0:
            elapsed_min = elapsed_sec // 60
            elapsed_sec_display = elapsed_sec % 60
            await status_msg.edit_text(f"""╔══════════════════════════════════════╗
║  🔍 АНАЛИЗ В ПРОЦЕССЕ               ║
╚══════════════════════════════════════╝

⏱️ Прошло: {elapsed_min:02d}:{elapsed_sec_display:02d}

🔄 JARVIS изучает компанию...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")
        
        await asyncio.sleep(POLLING_INTERVAL)
    
    # Получаем файлы
    files = extract_files_from_response(task_status)
    
    if not files:
        stats["errors"] += 1
        await status_msg.edit_text(msg_error("Не удалось получить досье"))
        await state.clear()
        await message.answer("Используйте меню для повторной попытки.", reply_markup=get_main_keyboard())
        return
    
    # Отправляем досье
    await status_msg.edit_text("""╔══════════════════════════════════════╗
║  ✅ АНАЛИЗ ЗАВЕРШЁН                 ║
╚══════════════════════════════════════╝

📋 Досье готово! Отправляю...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")
    
    for file_info in files:
        file_url = file_info.get("url")
        file_name = file_info.get("name", "document.pdf")
        
        if file_url:
            local_path = await download_file(file_url, file_name)
            if local_path:
                try:
                    await message.answer_document(
                        document=FSInputFile(local_path),
                        caption=f"📋 {file_name}"
                    )
                    stats["files_sent"] += 1
                except Exception as e:
                    logger.error(f"Error sending file: {e}")
    
    # Сохраняем досье в состояние
    await state.update_data(dossier_files=files, task_id=task_id)
    
    # Переходим к выбору документов
    await state.set_state(PresaleStates.selecting_docs)
    await message.answer("""╔══════════════════════════════════════╗
║  📦 ЭТАП 2: ВЫБОР ДОКУМЕНТОВ        ║
╚══════════════════════════════════════╝

Досье готово! Теперь выберите, какие
дополнительные документы подготовить:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""", reply_markup=get_document_selector_keyboard())
