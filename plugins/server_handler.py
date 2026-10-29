import re
from pyrogram import Client, filters
from config import ADMINS
from database.settings_db import get_active_hosts, set_active_hosts
from utils import hosts


async def _status_text():
    active = await get_active_hosts()
    lines = []
    for name, mod in hosts.HOSTS.items():
        label = hosts.LABELS[name]
        if not mod.enabled:
            state = "⚪ not set up (API key missing)"
        elif active is None or name in active:
            state = "✅ ON"
        else:
            state = "⛔ OFF"
        lines.append(f"• <b>{label}</b> — {state}")
    return "\n".join(lines)


@Client.on_message(filters.command(["active", "servers"]) & filters.private & filters.user(ADMINS))
async def active_servers(client, message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.reply_text(
            "<b>Upload servers for new files</b>\n\n"
            f"{await _status_text()}\n\n"
            "Usage:\n"
            "<code>/active doodstream mixdrop</code> — only these two\n"
            "<code>/active streamtape</code> — only Streamtape\n"
            "<code>/active all</code> — every server again\n"
            "<code>/active none</code> — no server upload"
        )
        return

    raw = args[1].strip().lower()

    if raw in ("all", "reset"):
        await set_active_hosts(None)
        await message.reply_text("✅ Every server is ON for new files.\n\n" + await _status_text())
        return

    if raw in ("none", "off"):
        await set_active_hosts([])
        await message.reply_text("⛔ All servers are OFF for new files.\n\n" + await _status_text())
        return

    chosen, unknown = [], []
    for token in re.split(r"[\s,&+]+|\band\b", raw):
        if not token or token == "and":
            continue
        name = hosts.parse_name(token)
        if name is None:
            unknown.append(token)
        elif name not in chosen:
            chosen.append(name)

    if unknown or not chosen:
        await message.reply_text(
            f"❌ Unknown server: <code>{' '.join(unknown) or raw}</code>\n\n"
            "Use: <code>streamtape</code>, <code>doodstream</code>, <code>mixdrop</code>"
        )
        return

    await set_active_hosts(chosen)
    missing = [hosts.LABELS[n] for n in chosen if not hosts.HOSTS[n].enabled]
    note = ("\n\n⚠️ No API key set for: " + ", ".join(missing)) if missing else ""
    await message.reply_text(
        "✅ Saved. Only these servers are ON for new files:\n\n" + await _status_text() + note
    )
