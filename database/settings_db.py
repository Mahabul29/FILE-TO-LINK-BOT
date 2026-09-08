from motor.motor_asyncio import AsyncIOMotorClient
from config import DATABASE_URI, DATABASE_NAME

if DATABASE_URI:
    client = AsyncIOMotorClient(DATABASE_URI)
    db = client[DATABASE_NAME]
    settings_col = db["settings"]
else:
    client = None
    db = None
    settings_col = None

_DOC_ID = "player_settings"
_DEFAULT = "all"


async def get_active_player() -> str:
    """
    Returns the active player key ("vlc", "mx", "splayer", "playit"),
    or "all" if no restriction is set.
    """
    if settings_col is None:
        return _DEFAULT
    doc = await settings_col.find_one({"_id": _DOC_ID})
    if not doc:
        return _DEFAULT
    return doc.get("active_player", _DEFAULT)


async def set_active_player(player_key: str) -> None:
    """
    player_key: one of "vlc", "mx", "splayer", "playit", or "all".
    """
    if settings_col is None:
        return
    await settings_col.update_one(
        {"_id": _DOC_ID},
        {"$set": {"active_player": player_key}},
        upsert=True,
    )


async def clear_active_player() -> None:
    await set_active_player(_DEFAULT)
    
