import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BIN_CHANNEL, FQDN, PLAYERS
from database.files_db import save_file
from database.settings_db import get_active_player


def build_clean_url(domain: str, path: str) -> str:
    """Builds a valid HTTPS URL and prevents 400 BUTTON_URL_INVALID errors."""
    clean_domain = domain.replace("https://", "").replace("http://", "").strip().strip("/")
    if not clean_domain or clean_domain == "localhost":
        clean_domain = "example.com"
    return f"https://{clean_domain}/{path.lstrip('/')}"


async def make_channel_buttons(file_id, is_video):
    download_link = build_clean_url(FQDN, f"dl/{file_id}")

    # Combine Download button and external player buttons into a single list
    all_buttons = [
        InlineKeyboardButton("ᴅᴏᴡɴʟᴏᴅ", url=download_link)
    ]

    if is_video:
        active_player = await get_active_player()
        keys = list(PLAYERS.keys()) if active_player == "all" else [active_player]
        keys = [k for k in keys if k in PLAYERS]

        for k in keys:
            all_buttons.append(
                InlineKeyboardButton(
                    PLAYERS[k]["label"],
                    url=build_clean_url(FQDN, f"open/{k}/{file_id}")
                )
            )

    # Format all buttons into 2 per row (e.g. [DOWNLOAD] [PLAYIT])
    rows = []
    for i in range(0, len(all_buttons), 2):
        rows.append(all_buttons[i:i + 2])

    return InlineKeyboardMarkup(rows)


_MEDIA_FILTER = (
    filters.document | filters.video | filters.audio |
    filters.photo | filters.animation | filters.video_note
)


@Client.on_message(filters.channel & _MEDIA_FILTER, group=1)
async def channel_file_handler(client, message):
    try:
        copied = await message.copy(chat_id=BIN_CHANNEL)

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

        is_video = bool(message.video) or "video" in mime_type
        markup = await make_channel_buttons(copied.id, is_video)

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
