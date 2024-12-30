import os
import logging
import json
import requests
import replicate

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ========== ВАЖНО: ЗАПОЛНИТЕ СВОИ ДАННЫЕ ==========
TELEGRAM_BOT_TOKEN = "7916958334:AAGtANeZunE18fHogBYqPmFi2vh7kWljUpA"
REPLICATE_API_TOKEN = "r8_ErWMVml6C854W5Zc8p28ZqGALui5kiT0wpAku"

# Модель Replicate (inpainting)
MODEL_NAME = "stability-ai/stable-diffusion-inpainting"
MODEL_VERSION = "95b7223104132402a9ae91cc677285bc5eb997834bd2349fa486f53910fd68b3"

# Укажите адрес, где лежит ваш index.html (HTTPS)
# Например, если вы задеплоили на https://example.com/ai-stylist/index.html
WEBAPP_URL = "https://ВАШ_АДРЕС/index.html"

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start — отправляем в чат кнопку, которая откроет WebApp (index.html)
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="AI Stylist WebApp",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text="Привет! Нажми кнопку, чтобы открыть AI-стилист (WebApp).",
        reply_markup=markup
    )


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает JSON-данные, которые WebApp присылает боту через sendData().
    Формат (пример):
    {
      "imageBase64": "data:image/png;base64, ...",
      "maskBase64": "data:image/png;base64, ...",
      "prompt": "red jacket, long hair"
    }
    """
    message_text = update.message.text

    try:
        data = json.loads(message_text)
    except json.JSONDecodeError:
        await update.message.reply_text("Не удалось распознать данные от WebApp (не JSON).")
        return

    image_base64 = data.get("imageBase64")
    mask_base64 = data.get("maskBase64")
    user_prompt = data.get("prompt", "").strip()

    if not image_base64 or not mask_base64:
        await update.message.reply_text("Не получены imageBase64 / maskBase64.")
        return

    if not user_prompt:
        user_prompt = "stylish clothes"  # fallback на случай пустого ввода

    await update.message.reply_text("Обрабатываю... подождите ~10-30 секунд.")

    replicate.client.api_token = REPLICATE_API_TOKEN

    def upload_to_replicate(b64_data, filename="file.png"):
        """Загружает Base64-изображение на Replicate-хостинг, возвращает URL."""
        upload_url = "https://dreambooth-api-experimental.replicate.com/v1/upload"

        # Отрезаем префикс (например, data:image/png;base64,)
        comma_index = b64_data.find(',')
        if comma_index != -1:
            b64_str = b64_data[comma_index+1:]
        else:
            b64_str = b64_data

        file_bytes = requests.utils.base64.b64decode(b64_str)
        files = {
            "file": (filename, file_bytes, "image/png")
        }
        headers = {
            "Authorization": f"Token {REPLICATE_API_TOKEN}"
        }
        resp = requests.post(upload_url, files=files, headers=headers)
        resp.raise_for_status()
        return resp.json()["url"]

    # 1) Загружаем image и mask на Replicate (оно хочет URL)
    try:
        image_url = upload_to_replicate(image_base64, "original.png")
        mask_url = upload_to_replicate(mask_base64, "mask.png")
    except Exception as e:
        logging.exception(e)
        await update.message.reply_text(f"Ошибка при загрузке: {e}")
        return

    # 2) Вызываем inpainting модель
    final_prompt = f"A person wearing {user_prompt}"
    model_input = {
        "image": image_url,
        "mask": mask_url,
        "prompt": final_prompt,
        "num_inference_steps": 25
    }

    try:
        output_urls = replicate.run(
            f"{MODEL_NAME}:{MODEL_VERSION}",
            input=model_input
        )
        output_list = list(output_urls)
    except Exception as e:
        logging.exception(e)
        await update.message.reply_text(f"Ошибка при генерации: {e}")
        return

    if not output_list:
        await update.message.reply_text("Пустой результат от Replicate :(")
        return

    result_url = output_list[0]
    try:
        img_data = requests.get(result_url).content
    except Exception as e:
        await update.message.reply_text(f"Ошибка скачивания результата: {e}")
        return

    await update.message.reply_photo(
        photo=img_data,
        caption=f"Готово! Вот твой новый образ: {user_prompt}."
    )


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # /start
    app.add_handler(CommandHandler("start", start_command))

    # Все текстовые сообщения считаем WebApp данными
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_webapp_data))

    logging.info("Запуск бота...")
    app.run_polling()


if __name__ == "__main__":
    main()
