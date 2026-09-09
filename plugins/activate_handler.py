from pyrogram import Client, filters
from config import PLAYERS, ADMINS
from database.settings_db import get_active_player, set_active_player, clear_active_player


def _players_list_text():
    lines = [f"• <code>{key}</code> — {info['label']}" for key, info in PLAYERS.items()]
    return "\n".join(lines)


@Client.on_message(filters.command("activate") & filters.private & filters.user(ADMINS))
async def activate_player(client, message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        current = await get_active_player()
        current_label = "All players" if current == "all" else PLAYERS.get(current, {}).get("label", current)
        await message.reply_text(
            "<b>Choose which player button(s) show up on new links.</b>\n\n"
            f"Currently active: <b>{current_label}</b>\n\n"
            "Available players:\n"
            f"{_players_list_text()}\n\n"
            "Usage:\n"
            "<code>/activate mx</code> — show only MX Player\n"
            "<code>/activate all</code> — show every player again"
        )
        return

    choice = args[1].strip().lower()

    if choice == "all":
        await clear_active_player()
        await message.reply_text("✅ Reset — every player button will show on new links.")
        return

    if choice not in PLAYERS:
        await message.reply_text(
            "❌ Unknown player key.\n\nAvailable:\n" + _players_list_text()
        )
        return

    await set_active_player(choice)
    await message.reply_text(f"✅ Only <b>{PLAYERS[choice]['label']}</b> will show on new links now.")


@Client.on_message(filters.command("players") & filters.private)
async def list_players(client, message):
    current = await get_active_player()
    current_label = "All players" if current == "all" else PLAYERS.get(current, {}).get("label", current)
    await message.reply_text(
        f"<b>Active:</b> {current_label}\n\n<b>All players:</b>\n{_players_list_text()}"
    )
