"""
Stores one global setting: which external player button(s) should be shown.

âš ï¸ IMPORTANT â€” adjust the import below to match how your project already
connects to Mongo in database/files_db.py. This file assumes the same
motor-based pattern most of these bots use (config.MONGO_URI / config.DB_NAME).
If your files_db.py exposes a shared `db` object, import that instead of
creating a second client here â€” just swap the two marked lines.
"""

from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DB_NAME  # <-- adjust if your config uses different names

client = AsyncIOMotorClient(MONGO_URI)        # <-- swap for shared client if you have one
db = client[DB_NAME]                          # <-- swap for shared db if you have one
settings_col = db["settings"]

_DOC_ID = "player_settings"  # single-row settings doc
_DEFAULT = "all"             # "all" = show every player button


async def get_active_player() -> str:
    """
    Returns the active player key ("vlc", "mx", "splayer", "playit"),
    or "all" if no restriction is set (default / initial state).
    """
    doc = await settings_col.find_one({"_id": _DOC_ID})
    if not doc:
        return _DEFAULT
    return doc.get("active_player", _DEFAULT)


async def set_active_player(player_key: str) -> None:
    """
    player_key: one of "vlc", "mx", "splayer", "playit", or "all" to reset.
    """
    await settings_col.update_one(
        {"_id": _DOC_ID},
        {"$set": {"active_player": player_key}},
        upsert=True,
    )


async def clear_active_player() -> None:
    await set_active_player(_DEFAULT)
