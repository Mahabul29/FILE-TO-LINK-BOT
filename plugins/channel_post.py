import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BIN_CHANNEL, FQDN, PLAYERS
from database.files_db import save_file
from database.settings_db import get_active_player

logger = logging.getLogger(__name__)


def to_mono(text: str) -> str:
    """Converts standard ASCII characters to Mathematical Monospace font."""
    res = []
    for char in text:
        code = ord(char)
        if 65 <= code <= 90:      # A-Z
            res.append(chr(0x1D670 + (code - 65)))
        elif 97 <= code <= 122:   # a-z
            res.append(chr(0x1D68A + (code - 97)))
        elif 48 <= code <= 57:    # 0-9
            res.append(chr(0x1D7F6 + (code - 48)))
        else:
            res.append(char)
    return "".join(res)


async def make_channel_buttons(file_id: int, is_video: bool) -> InlineKeyboardMarkup:
    clean_host = FQDN.replace("https://", "").replace("http://", "").rstrip("/")
    download_link = f"https://{clean_host}/dl/{file_id}"
    stream_link = f"https://{clean_host}/watch/{file_id}"

    # Buttons using monospace font without emojis
    rows = [
        [
            InlineKeyboardButton(to_mono("ᴅᴏᴡɴʟᴏᴅ"), url=download_link),
            InlineKeyboardButton(to_mono("sᴛʀᴇᴀᴍ"), url=stream_link)
        ]
    ]

    if is_video:
        active_player = await get_active_player()
        keys = list(PLAYERS.keys()) if active_player == "all" else [active_player]
        keys = [k for k in keys if k in PLAYERS]

        player_buttons = []
        for k in keys:
            label = PLAYERS[k]["label"]
            if "Player" not in label:
                label = f"{label} Player"
            
            player_buttons.append(
                InlineKeyboardButton(
                    to_mono(label),
                    url=f"https://{clean_host}/open/{k}/{file_id}"
                )
            )

        # Format into 2 buttons per row
        for i in range(0, len(player_buttons), 2):
            rows.append(player_buttons[i:i + 2])

    return InlineKeyboardMarkup(rows)


_MEDIA_FILTER = (
    filters.document | filters.video | filters.audio |
    filters.photo | filters.animation | filters.video_note
)


@Client.on_message(filters.channel & _MEDIA_FILTER, group=1)
async def channel_file_handler(client, message):
    try:
        # Copy to BIN_CHANNEL so streaming/download server can access the file
        copied = await message.copy(chat_id=BIN_CHANNEL)
        if not copied:
            return

        media = (
            message.document or message.video or message.audio
            or message.photo or message.animation or message.video_note
        )
        file_name = getattr(media, "file_name", "Unknown File") if media else "Unknown File"
        file_size = getattr(media, "file_size", 0) or 0
        mime_type = getattr(media, "mime_type", "application/octet-stream") or "application/octet-stream"

        await save_file(
            file_id=copied.id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            uploader_id=message.chat.id
        )

        video_exts = ('.mkv', '.mp4', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.webm', '.3gp')
        is_video = (
            message.video is not None 
            or "video" in mime_type.lower() 
            or file_name.lower().endswith(video_exts)
        )

        markup = await make_channel_buttons(copied.id, is_video)

        await asyncio.sleep(1)

        # Edits only the reply markup so original post caption/text remains intact
        await client.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=message.id,
            reply_markup=markup
        )

        logger.info(f"Buttons added to Channel Post: {message.id} in Chat: {message.chat.id}")

    except Exception as e:
        logger.error(f"Error in Channel {message.chat.id}: {e}")


@Client.on_edited_message(filters.channel & _MEDIA_FILTER, group=1)
async def channel_edit_handler(client, message):
    if not message.reply_markup:
        await channel_file_handler(client, message)
    
