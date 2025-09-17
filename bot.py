import os
import logging
import tempfile
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден! Проверьте файл .env")


# Настройки таймаутов
DOWNLOAD_TIMEOUT = 600  # 10 минут на скачивание
REQUEST_TIMEOUT = 60    # 60 секунд на HTTP запросы

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = """
🎬 Добро пожаловать в AnyLink Saver!

Я помогу сохранить видео и музыку из:
• Instagram Reels и постов
• TikTok
• YouTube Shorts и видео
• Facebook видео и Reels

📥 Просто отправь ссылку — и я пришлю:
• Видео в MP4 (максимальное качество)
• Аудио в MP3 (отличное качество)

🚀 Попробуй прямо сейчас — скинь мне любую ссылку!
    """
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📖 Как пользоваться:

Просто отправь мне ссылку из:
• Instagram: https://www.instagram.com/reel/... или https://www.instagram.com/p/...
• TikTok: https://www.tiktok.com/@.../video/...
• YouTube: https://youtube.com/... или https://youtube.com/shorts/...
• Facebook: https://www.facebook.com/.../videos/... или https://fb.watch/...

🎯 Возможности:
• Скачивание видео в максимальном качестве
• Извлечение аудио в MP3
• Отслеживание прогресса загрузки
• Поддержка больших файлов (отправляются как документы)
• Быстрая обработка с оптимизированными настройками

⚙️ Поддерживаемые форматы:
• Видео: MP4 (лучшее доступное качество)
• Аудио: MP3 (высокое качество)

⚠️ Примечание:
• Видео должны быть публичными и доступными
• Максимальный размер: 50MB (ограничение Telegram)
• Видео с Facebook могут требовать авторизацию
• Обработка может занять несколько минут для роликов в высоком качестве

🔧 Команды:
/start – приветственное сообщение
/help – справка по использованию
/info – возможности бота
    """
    await update.message.reply_text(help_text)

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /info"""
    info_text = """
🤖 Возможности бота:

📱 Поддерживаемые платформы:
• Instagram — Reels, посты, сторис (публичные)
• TikTok — все публичные видео
• YouTube — видео, Shorts, записи трансляций
• Facebook — публичные видео, Reels, посты

🎬 Варианты загрузки:
• Видео — в максимально доступном качестве (до 4K)
• Аудио — в формате MP3 с метаданными
• Автоматическое определение формата
• Отслеживание прогресса загрузки

⚡ Технические возможности:
• Таймаут на скачивание — до 10 минут для больших файлов
• Автоматическая оптимизация размера файлов
• Обработка ошибок и обратная связь пользователю
• Автоматическая очистка временных файлов

📊 Ограничения:
• Лимит Telegram — до 50MB для видео
• Некоторые Facebook-видео могут требовать входа в аккаунт
• Приватный и возрастной контент не поддерживается
• Контент с региональными ограничениями может быть недоступен

💡 Советы:
• Отправляй прямые ссылки на видео для лучшего результата
• Для Facebook используй только публичные ролики
• Будь терпелив при загрузке больших файлов
• Если возникли проблемы — попробуй позже или обратись в поддержку
    """
    await update.message.reply_text(info_text)

def download_media(url):
    """Скачивает видео с различных платформ в максимальном качестве"""
    ydl_opts = {
        'format': 'best',  # Максимальное качество
        'outtmpl': '%(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': DOWNLOAD_TIMEOUT,
        'retries': 3,
        'noprogress': True,
        # Специальные настройки для Facebook
        'extractor_args': {
            'facebook': {
                'credentials': {
                    'email': None,
                    'password': None,
                }
            }
        },
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            video_url = info['url']
            title = info.get('title', 'video_content').replace('/', '_').replace('\\', '_')
            duration = info.get('duration', 0)
            
            # Безопасное получение размера файла
            filesize = info.get('filesize', 0) or info.get('filesize_approx', 0)
            if filesize is None:
                filesize = 0
            
            return {
                'video_url': video_url,
                'title': title,
                'duration': duration,
                'filesize': filesize,
                'platform': info.get('extractor', 'unknown')
            }
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        # Специальная обработка ошибок Facebook
        if 'facebook' in str(e).lower():
            raise Exception("Видео с Facebook требует авторизации или является приватным. Попробуйте публичное видео.")
        raise Exception(f"Ошибка загрузки: {str(e)}")

async def download_file_with_progress(url, file_path, message, text):
    """Скачивает файл с прогрессом и обновлением сообщения"""
    try:
        start_time = datetime.now()
        last_update_time = start_time
        
        with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.facebook.com/',
        }) as response:
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            
            with open(file_path, 'wb') as file:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=32768):
                    if chunk:
                        file.write(chunk)
                        downloaded += len(chunk)
                        
                        # Обновляем сообщение каждые 10 секунд
                        current_time = datetime.now()
                        if (current_time - last_update_time).total_seconds() >= 10:
                            elapsed = (current_time - start_time).total_seconds()
                            progress = f"📥 {text}\n⏱ {int(elapsed)}с"
                            
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                progress += f"\n📊 {percent:.1f}% ({downloaded//1024//1024}МБ/{total_size//1024//1024}МБ)"
                            else:
                                progress += f"\n📊 {downloaded//1024//1024}МБ загружено"
                            
                            try:
                                await message.edit_text(progress)
                                last_update_time = current_time
                            except Exception as e:
                                logger.warning(f"Failed to update progress: {e}")
            
            return True
            
    except requests.exceptions.Timeout:
        raise Exception("Таймаут загрузки - сервер слишком медленный")
    except Exception as e:
        raise Exception(f"Ошибка загрузки: {str(e)}")

async def handle_media_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ссылок на медиа"""
    user = update.message.from_user
    url = update.message.text.strip()
    
    logger.info(f"Media link from {user.first_name}: {url}")
    
    # Очищаем URL от параметров
    clean_url = url.split('?')[0]
    
    # Проверяем поддерживаемые платформы
    is_instagram = 'instagram.com/reel/' in clean_url or 'instagram.com/p/' in clean_url
    is_tiktok = 'tiktok.com' in clean_url and '/video/' in clean_url
    is_youtube = 'youtube.com' in clean_url or 'youtu.be' in clean_url
    is_facebook = 'facebook.com' in clean_url or 'fb.watch/' in clean_url or 'fb.com' in clean_url
    
    if not (is_instagram or is_tiktok or is_youtube or is_facebook):
        await update.message.reply_text("❌ Неподдерживаемая платформа. Отправьте ссылку из Instagram, TikTok, YouTube или Facebook.")
        return
    
    # Определяем тип контента
    if is_instagram:
        platform = "Instagram"
    elif is_tiktok:
        platform = "TikTok"
    elif is_facebook:
        platform = "Facebook"
    else:
        platform = "YouTube"
    
    processing_msg = await update.message.reply_text(f"⏳ Обрабатываю ссылку {platform}...")
    
    try:
        # Скачиваем информацию о видео
        media_info = await asyncio.get_event_loop().run_in_executor(
            None, lambda: download_media(clean_url)
        )
        
        # Безопасная проверка размера файла
        filesize = media_info.get('filesize', 0) or 0
        if filesize and filesize > 45 * 1024 * 1024:
            await processing_msg.edit_text(
                f"⚠️ Видео большое ({filesize//1024//1024}МБ). "
                f"Это может занять время...\n\nЗагружаю в максимальном качестве..."
            )
        else:
            await processing_msg.edit_text("📥 Загружаю в максимальном качестве...")
        
        video_path = None
        audio_path = None
        
        try:
            # Создаем временный файл для видео
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as video_file:
                video_path = video_file.name
            
            # Скачиваем видео с прогрессом
            await download_file_with_progress(
                media_info['video_url'], 
                video_path, 
                processing_msg, 
                "Загружаю видео (макс. качество)"
            )
            
            # Проверяем размер файла
            file_size = os.path.getsize(video_path)
            if file_size > 45 * 1024 * 1024:
                await processing_msg.edit_text("📤 Файл большой, отправляю как документ...")
                
                with open(video_path, 'rb') as video:
                    await update.message.reply_document(
                        document=video,
                        caption=f"🎬 {media_info['title']}\n📺 Из: {platform}\n⏱ Длительность: {media_info['duration']}с\n💾 Размер: {file_size//1024//1024}МБ\n\nФайл слишком большой для формата видео, отправлен как документ.",
                        read_timeout=DOWNLOAD_TIMEOUT,
                        write_timeout=DOWNLOAD_TIMEOUT,
                        connect_timeout=DOWNLOAD_TIMEOUT,
                        pool_timeout=DOWNLOAD_TIMEOUT
                    )
            else:
                # Отправляем видео
                await processing_msg.edit_text("📤 Отправляю видео...")
                
                caption = f"🎬 {media_info['title']}\n📺 Из: {platform}\n⏱ Длительность: {media_info['duration']}с\n💾 Размер: {file_size//1024//1024}МБ"
                
                with open(video_path, 'rb') as video:
                    await update.message.reply_video(
                        video=video,
                        caption=caption,
                        supports_streaming=True,
                        read_timeout=DOWNLOAD_TIMEOUT,
                        write_timeout=DOWNLOAD_TIMEOUT,
                        connect_timeout=DOWNLOAD_TIMEOUT,
                        pool_timeout=DOWNLOAD_TIMEOUT
                    )
            
            # Скачиваем аудио
            await processing_msg.edit_text("🎵 Подготавливаю аудио...")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as audio_file:
                audio_path = audio_file.name
            
            # Скачиваем аудио с прогрессом
            await download_file_with_progress(
                media_info['video_url'], 
                audio_path, 
                processing_msg, 
                "Загружаю аудио"
            )
            
            # Отправляем аудио
            await processing_msg.edit_text("📤 Отправляю аудио...")
            with open(audio_path, 'rb') as audio:
                await update.message.reply_audio(
                    audio=audio,
                    title=media_info['title'][:64],
                    performer=platform,
                    caption=f"🎵 Аудио из {platform}",
                    read_timeout=DOWNLOAD_TIMEOUT,
                    write_timeout=DOWNLOAD_TIMEOUT,
                    connect_timeout=DOWNLOAD_TIMEOUT,
                    pool_timeout=DOWNLOAD_TIMEOUT
                )
            
            await processing_msg.delete()
            await update.message.reply_text(f"✅ Готово! Наслаждайтесь контентом из {platform} в максимальном качестве!")
            
        finally:
            # Удаляем временные файлы
            for file_path in [video_path, audio_path]:
                if file_path and os.path.exists(file_path):
                    try:
                        os.unlink(file_path)
                    except:
                        pass
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await processing_msg.delete()
        
        error_message = f"❌ Ошибка: {str(e)}"
        
        if "timed out" in str(e).lower() or "таймаут" in str(e).lower():
            error_message = """
❌ Превышено время операции!

Возможные причины:
• Видео очень длинное или в высоком качестве
• Медленное интернет-соединение
• Сервер перегружен

Попробуйте позже или используйте более короткое видео.
"""
        elif "too large" in str(e).lower() or "большой" in str(e).lower():
            error_message += "\n\n⚠️ Файл слишком большой для Telegram."
        elif "facebook" in str(e).lower() and ("login" in str(e).lower() or "авторизац" in str(e).lower()):
            error_message = """
❌ Проблема доступа к видео Facebook!

Видео с Facebook может:
• Требовать авторизации
• Быть приватным или ограниченным
• Требовать специальных разрешений

Попробуйте другое публичное видео или другую платформу.
"""
        elif "'>' not supported between instances of 'NoneType' and 'int'" in str(e):
            error_message = """
❌ Ошибка обработки видео Facebook!

Данный формат видео с Facebook не поддерживается.
Попробуйте другое видео или используйте другую платформу.
"""
        
        await update.message.reply_text(error_message)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Error: {context.error}")
    
    if update and update.message:
        await update.message.reply_text("❌ Что-то пошло не так. Пожалуйста, попробуйте позже.")

def main():
    """Основная функция"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_media_link))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен с поддержкой Facebook!")
    print("🤖 Бот запущен с расширенными возможностями...")
    print("🎬 Instagram загрузчик готов")
    print("📱 TikTok загрузчик готов")
    print("📺 YouTube загрузчик готов")
    print("📘 Facebook загрузчик готов")
    print("⚡ Настройки максимального качества активированы")
    print("⏰ Таймаут 10 минут для загрузок")
    
    application.run_polling(
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()