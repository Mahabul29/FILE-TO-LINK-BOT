from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BIN_CHANNEL, FQDN
from database.files_db import save_file

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
            "<b>𝗬𝗼𝘂𝗿 𝗟𝗶𝗻𝗸 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱 ♥︎</b>\n\n"
            f"<b>𝙵𝚒𝚕𝚎 𝙽𝚊𝚖𝚎:</b> <code>{file_name}</code>\n\n"
            f"<b>ғɪʟᴇ sɪᴢᴇ:</b> <code>{size_mb} MB</code>\n\n"
            f"<b>𝙳𝚘𝚠𝚗𝚕𝚘𝚊𝚍:</b>\n{download_link}"
        )

        buttons = [
            [
                InlineKeyboardButton("𝙳𝚘𝚠𝚗𝚕𝚘𝚊𝚍", url=download_link),
                InlineKeyboardButton("𝚂𝚝𝚛𝚎𝚊𝚖", url=stream_link)
            ]
        ]

        # VLC / MX Player only make sense for video — they'd just error on a plain document.
        if "video" in mime_type:
            vlc_open_url = f"https://{base_url}/open/vlc/{copied_msg.id}"
            mx_open_url = f"https://{base_url}/open/mx/{copied_msg.id}"
            buttons.append([
                InlineKeyboardButton("𝚅𝙻𝙲 𝙿𝚕𝚊𝚢𝚎𝚛", url=vlc_open_url),
                InlineKeyboardButton("𝙼𝚇 𝙿𝚕𝚊𝚢𝚎𝚛", url=mx_open_url)
            ])

        keyboard = InlineKeyboardMarkup(buttons)

        await msg.edit_text(
            text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

    except Exception as e:
        await msg.edit_text(f"<b>Error:</b> <code>{str(e)}</code>")
        
