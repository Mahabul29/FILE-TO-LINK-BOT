from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BIN_CHANNEL, FQDN, PLAYERS
from database.files_db import save_file
from database.settings_db import get_active_player


async def build_player_buttons(base_url, file_id):
    """
    Returns a list of InlineKeyboardButton rows for external players,
    respecting the active-player setting (2 buttons per row).
    """
    active_player = await get_active_player()
    keys = list(PLAYERS.keys()) if active_player == "all" else [active_player]
    keys = [k for k in keys if k in PLAYERS]

    buttons = [
        InlineKeyboardButton(PLAYERS[k]["label"], url=f"https://{base_url}/open/{k}/{file_id}")
        for k in keys
    ]

    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return rows


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def link_generator_handler(client, message):
    msg = await message.reply_text("<code>Processing...</code>")

    try:
        base_url = FQDN.replace("https://", "").replace("http://", "").strip("/")

        copied_msg = await message.copy(chat_id=BIN_CHANNEL)

        download_link = f"https://{base_url}/dl/{copied_msg.id}"
        stream_link = f"https://{base_url}/watch/{copied_msg.id}"

        media = message.document or message.video or message.audio
        file_name = getattr(media, "file_name", "Unknown")
        file_size = getattr(media, "file_size", 0) or 0
        mime_type = getattr(media, "mime_type", "application/octet-stream") or "application/octet-stream"
        size_mb = round(file_size / (1024 * 1024), 2)

        # Save record so it shows up on the /files web page
        await save_file(
            file_id=copied_msg.id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            uploader_id=message.from_user.id
        )

        text = (
            "<b>ð—¬ð—¼ð˜‚ð—¿ ð—Ÿð—¶ð—»ð—¸ ð—šð—²ð—»ð—²ð—¿ð—®ð˜ð—²ð—± â™¥ï¸Ž</b>\n\n"
            f"<b>ð™µðš’ðš•ðšŽ ð™½ðšŠðš–ðšŽ:</b> <code>{file_name}</code>\n\n"
            f"<b>Ò“ÉªÊŸá´‡ sÉªá´¢á´‡:</b> <code>{size_mb} MB</code>\n\n"
            f"<b>ð™³ðš˜ðš ðš—ðš•ðš˜ðšŠðš:</b>\n{download_link}"
        )

        buttons = [
            [
                InlineKeyboardButton("ð™³ðš˜ðš ðš—ðš•ðš˜ðšŠðš", url=download_link),
                InlineKeyboardButton("ðš‚ðšðš›ðšŽðšŠðš–", url=stream_link)
            ]
        ]

        # VLC / MX / SPlayer / PLAYit only make sense for video.
        # If /activate was used, only that one player's button is added.
        if "video" in mime_type:
            player_rows = await build_player_buttons(base_url, copied_msg.id)
            buttons.extend(player_rows)

        keyboard = InlineKeyboardMarkup(buttons)

        await msg.edit_text(
            text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

    except Exception as e:
        await msg.edit_text(f"<b>Error:</b> <code>{str(e)}</code>")
