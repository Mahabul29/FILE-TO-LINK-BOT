import asyncio
import html
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BIN_CHANNEL, FQDN, PUBLIC_FQDN
from database.files_db import save_file
from utils import streamtape

_ICON = {"wait": "⏳ uploading...", "ok": "✅ ready", "fail": "❌ failed, auto retry"}


def _links_text(file_id, file_name, state, err=None):
    """state is wait | ok | fail."""
    page = streamtape.stable_link(file_id)
    text = (
        f"\n\n<b>Link:</b>\n{page}"
        f"\n\n<b>Streamtape:</b> {_ICON[state]}"
    )
    if state == "fail" and err:
        text += f"\n<code>{html.escape(str(err))}</code>"
    if state == "ok":
        text += (
            f"\n\n<b>Player link (paste in any video player / URL stream):</b>\n"
            f"{streamtape.video_link(file_id, file_name)}"
        )
    return text


def _keyboard(file_id):
    base = f"https://{PUBLIC_FQDN}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Streamtape", url=f"{base}/s/{file_id}"),
    ]])


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def link_generator_handler(client, message):
    msg = await message.reply_text("<code>Processing...</code>")

    try:
        if not streamtape.enabled:
            await msg.edit_text(
                "<b>Error:</b> <code>Set STREAMTAPE_LOGIN + STREAMTAPE_KEY "
                "in the Environment tab.</code>"
            )
            return
        if not FQDN:
            await msg.edit_text(
                "<b>Error:</b> <code>FQDN is not set. Add your bot-hosting.net domain "
                "in the Environment tab.</code>"
            )
            return

        copied_msg = await message.copy(chat_id=BIN_CHANNEL)

        media = message.document or message.video or message.audio
        file_name = getattr(media, "file_name", None) or "Unknown File"
        file_size = getattr(media, "file_size", 0) or 0
        mime_type = getattr(media, "mime_type", "application/octet-stream") or "application/octet-stream"
        size_mb = round(file_size / (1024 * 1024), 2)

        await save_file(
            file_id=copied_msg.id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            uploader_id=message.from_user.id
        )

        text = (
            "<b>𝗬𝗼𝘂𝗿 𝗟𝗶𝗻𝗸 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱 🌿</b>\n\n"
            f"<b>𝙵𝚒𝚕𝚎 𝙽𝚊𝚖𝚎:</b> <code>{file_name}</code>\n\n"
            f"<b>𝙵𝚒𝚕𝚎 𝚂𝚒𝚣𝚎:</b> <code>{size_mb} MB</code>"
        )
        keyboard = _keyboard(copied_msg.id)

        st_name = None if file_name == "Unknown File" else file_name
        await msg.edit_text(
            text + _links_text(copied_msg.id, st_name, "wait"),
            reply_markup=keyboard, disable_web_page_preview=True
        )
        asyncio.create_task(_upload_and_update(msg, text, keyboard, copied_msg.id, st_name, mime_type))

    except Exception as e:
        await msg.edit_text(f"<b>Error:</b> <code>{str(e)}</code>")


async def _upload_and_update(msg, text, keyboard, file_id, file_name, mime_type):
    try:
        ok = bool(await streamtape.upload(file_id, file_name, mime_type))
    except Exception as e:
        print(f"streamtape push error: {e}")
        ok = False
    state = "ok" if ok else "fail"
    err = None if ok else (streamtape.last_error.get(int(file_id)) or "unknown - see console log")
    try:
        await msg.edit_text(
            text + _links_text(file_id, file_name, state, err),
            reply_markup=keyboard, disable_web_page_preview=True
        )
    except Exception as e:
        print(f"Link message edit error: {e}")
        
