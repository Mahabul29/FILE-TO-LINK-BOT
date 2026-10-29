import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BIN_CHANNEL, FQDN, PLAYERS
from database.files_db import save_file
from database.settings_db import get_active_player
from utils import streamtape, doodstream, mixdrop, hosts


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


def _host_note(label, mod, file_id, file_name, page_link, state):
    """state: None = uploading, True = done, False = failed."""
    if state is None:
        return f"\n\n<b>{label}:</b> ⏳ <i>uploading...</i>\n{page_link}"
    if state:
        return (
            f"\n\n<b>{label} page:</b>\n{page_link}"
            f"\n\n<b>{label} player link (paste in any video player / URL stream):</b>\n{mod.video_link(file_id, file_name)}"
        )
    return f"\n\n<b>{label}:</b> <i>upload failed, the bot will retry automatically</i>\n{page_link}"


async def _hosts_push(msg, text, rows, file_id, file_name, mime_type, links):
    """Uploads to Streamtape / DoodStream in the background and updates the bot's reply as each finishes."""
    hosts = []
    if links.get("st"):
        hosts.append(("Streamtape", streamtape, links["st"]))
    if links.get("dd"):
        hosts.append(("DoodStream", doodstream, links["dd"]))
    if links.get("mx"):
        hosts.append(("Mixdrop", mixdrop, links["mx"]))
    states = {label: None for label, _, _ in hosts}
    edit_lock = asyncio.Lock()

    async def refresh():
        note = "".join(_host_note(l, m, file_id, file_name, link, states[l]) for l, m, link in hosts)
        async with edit_lock:
            try:
                await msg.edit_text(text + note, reply_markup=InlineKeyboardMarkup(rows),
                                    disable_web_page_preview=True)
            except Exception as e:
                print(f"Link message edit error: {e}")

    async def one(label, mod):
        try:
            states[label] = bool(await mod.upload(file_id, file_name, mime_type))
        except Exception as e:
            print(f"{label} push error: {e}")
            states[label] = False
        await refresh()

    await asyncio.gather(*(one(l, m) for l, m, _ in hosts))


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def link_generator_handler(client, message):
    msg = await message.reply_text("<code>Processing...</code>")

    try:
        base_url = FQDN.replace("https://", "").replace("http://", "").strip("/")

        copied_msg = await message.copy(chat_id=BIN_CHANNEL)

        download_link = f"https://{base_url}/dl/{copied_msg.id}"
        stream_link = f"https://{base_url}/watch/{copied_msg.id}"

        media = message.document or message.video or message.audio
        file_name = getattr(media, "file_name", None) or "Unknown File"
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

        # Clean standard text (fixes encoding corruption/glitch in message text)
        text = (
            "<b>𝗬𝗼𝘂𝗿 𝗟𝗶𝗻𝗸 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱 🌿</b>\n\n"
            f"<b>𝙵𝚒𝚕𝚎 𝙽𝚊𝚖𝚎:</b> <code>{file_name}</code>\n\n"
            f"<b>𝙵𝚒𝚕𝚎 𝚂𝚒𝚣𝚎:</b> <code>{size_mb} MB</code>\n\n"
            f"<b>𝙳𝚘𝚠𝚗𝚕𝚘𝚍:</b>\n{download_link}"
        )

        buttons = [
            [
                InlineKeyboardButton("𝗗𝗼𝘄𝗻𝗹𝗼𝗱", url=download_link),
                InlineKeyboardButton("𝗦𝘁𝗿𝗲𝗮𝗺", url=stream_link)
            ]
        ]

        # Enhanced video detection (handles .mkv, .mp4, and video documents)
        video_exts = ('.mkv', '.mp4', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.webm', '.3gp')
        is_video = (
            message.video is not None 
            or "video" in mime_type.lower() 
            or file_name.lower().endswith(video_exts)
        )

        if is_video:
            buttons.append([
                InlineKeyboardButton(
                    "Download From EvaPLAYER",
                    url=f"https://{base_url}/open/evaplayer/{copied_msg.id}?action=download"
                )
            ])
            player_rows = await build_player_buttons(base_url, copied_msg.id)
            buttons.extend(player_rows)

        st_link = None
        if await hosts.is_on("streamtape"):
            st_link = streamtape.stable_link(copied_msg.id)
            buttons.append([InlineKeyboardButton("Streamtape", url=st_link)])

        dd_link = None
        if await hosts.is_on("doodstream"):
            dd_link = doodstream.stable_link(copied_msg.id)
            buttons.append([InlineKeyboardButton("DoodStream", url=dd_link)])

        mx_link = None
        if await hosts.is_on("mixdrop"):
            mx_link = mixdrop.stable_link(copied_msg.id)
            buttons.append([InlineKeyboardButton("Mixdrop", url=mx_link)])

        keyboard = InlineKeyboardMarkup(buttons)

        await msg.edit_text(
            text
            + (_host_note("Streamtape", streamtape, copied_msg.id, None, st_link, None) if st_link else "")
            + (_host_note("DoodStream", doodstream, copied_msg.id, None, dd_link, None) if dd_link else "")
            + (_host_note("Mixdrop", mixdrop, copied_msg.id, None, mx_link, None) if mx_link else ""),
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

        if st_link or dd_link or mx_link:
            st_name = None if file_name == "Unknown File" else file_name
            asyncio.create_task(
                _hosts_push(msg, text, buttons, copied_msg.id, st_name, mime_type,
                            {"st": st_link, "dd": dd_link, "mx": mx_link})
            )

    except Exception as e:
        await msg.edit_text(f"<b>Error:</b> <code>{str(e)}</code>")

