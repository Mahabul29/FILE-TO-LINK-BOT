import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BIN_CHANNEL
from database.files_db import save_file
from utils import streamtape

_MEDIA_FILTER = (
    filters.document | filters.video | filters.audio |
    filters.photo | filters.animation | filters.video_note
)


@Client.on_message(filters.channel & _MEDIA_FILTER, group=1)
async def channel_file_handler(client, message):
    try:
        if not streamtape.enabled:
            return
        if not (message.document or message.video or message.audio):
            return

        copied = await message.copy(chat_id=BIN_CHANNEL)
        if not copied:
            return

        media = message.document or message.video or message.audio
        file_name = getattr(media, "file_name", None) or "Unknown"
        file_size = getattr(media, "file_size", 0) or 0
        mime_type = getattr(media, "mime_type", "application/octet-stream") or "application/octet-stream"

        await save_file(
            file_id=copied.id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            uploader_id=message.chat.id
        )

        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Streamtape", url=streamtape.stable_link(copied.id))]]
        )
        await asyncio.sleep(1)
        await client.edit_message_reply_markup(
            chat_id=message.chat.id, message_id=message.id, reply_markup=markup
        )
        print(f"✅ Button added to Channel Post: {message.id}")

        st_name = None if file_name == "Unknown" else file_name
        asyncio.create_task(streamtape.upload(copied.id, st_name, mime_type))

    except Exception as e:
        print(f"❌ Error in Channel {message.chat.id}: {e}")


@Client.on_edited_message(filters.channel & _MEDIA_FILTER, group=1)
async def channel_edit_handler(client, message):
    if not message.reply_markup:
        await channel_file_handler(client, message)
        
