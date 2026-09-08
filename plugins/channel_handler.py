import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BIN_CHANNEL, FQDN, PLAYERS
from database.files_db import save_file
from database.settings_db import get_active_player


async def make_channel_buttons(file_id, is_video):
    clean_host = FQDN.replace("https://", "").replace("http://", "").rstrip("/")
    download_link = f"https://{clean_host}/dl/{file_id}"
    stream_link = f"https://{clean_host}/watch/{file_id}"

    rows = [
        [
            InlineKeyboardButton("ð™³ðš˜ðš ðš—ðš•ðš˜ðšŠðš", url=download_link),
            InlineKeyboardButton("ðš‚ðšðš›ðšŽðšŠðš–", url=stream_link)
        ]
    ]

    # VLC / MX / SPlayer / PLAYit only make sense for video. Buttons point at our own
    # https:// redirect page (web/open_redirect.py), not a raw intent:// URL â€”
    # Telegram's Bot API rejects non-http(s)/tg button URLs with BUTTON_URL_INVALID.
    if is_video:
        active_player = await get_active_player()
        keys = list(PLAYERS.keys()) if active_player == "all" else [active_player]
        keys = [k for k in keys if k in PLAYERS]

        player_buttons = [
            InlineKeyboardButton(PLAYERS[k]["label"], url=f"https://{clean_host}/open/{k}/{file_id}")
            for k in keys
        ]
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
        # Copy into BIN_CHANNEL â€” this is the channel video_play.py / stream_handler
        # actually reads files from. Copying anywhere else produces links that 404.
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

        print(f"âœ… Buttons added to Channel Post: {message.id}")

    except Exception as e:
        print(f"âŒ Error in Channel {message.chat.id}: {e}")


@Client.on_edited_message(filters.channel & _MEDIA_FILTER, group=1)
async def channel_edit_handler(client, message):
    if not message.reply_markup:
        await channel_file_handler(client, message)
