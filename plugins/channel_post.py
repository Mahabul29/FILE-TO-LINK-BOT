import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import LOG_CHANNEL, FQDN
from database.files_db import save_file

def make_channel_buttons(file_id):
    clean_host = FQDN.replace("https://", "").replace("http://", "").rstrip("/")
    download_link = f"https://{clean_host}/dl/{file_id}"
    stream_link = f"https://{clean_host}/watch/{file_id}"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("𝙳𝚘𝚠𝚗𝚕𝚘𝚊𝚍", url=download_link),
            InlineKeyboardButton("𝚂𝚝𝚛𝚎𝚊𝚖", url=stream_link)
        ]
    ])

_MEDIA_FILTER = (
    filters.document | filters.video | filters.audio |
    filters.photo | filters.animation | filters.video_note
)

@Client.on_message(filters.channel & _MEDIA_FILTER, group=1)
async def channel_file_handler(client, message):
    try:
        copied = await message.copy(chat_id=LOG_CHANNEL)

        if not copied:
            return

        media = (
            message.document or message.video or message.audio
            or message.photo or message.animation or message.video_note
        )
        file_name = getattr(media, "file_name", "Unknown") if media else "Unknown"
        file_size = getattr(media, "file_size", 0) or 0
        mime_type = getattr(media, "mime_type", "application/octet-stream") or "application/octet-stream"

        await save_file(
            file_id=copied.id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            uploader_id=message.chat.id
        )

        markup = make_channel_buttons(copied.id)

        await asyncio.sleep(1)

        await client.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=message.id,
            reply_markup=markup
        )

        print(f"✅ Buttons added to Channel Post: {message.id}")

    except Exception as e:
        print(f"❌ Error in Channel {message.chat.id}: {e}")

@Client.on_edited_message(filters.channel & _MEDIA_FILTER, group=1)
async def channel_edit_handler(client, message):
    if not message.reply_markup:
        await channel_file_handler(client, message)
