"""Which upload servers (Streamtape / DoodStream / Mixdrop) are switched on for NEW files."""
from database.settings_db import get_active_hosts
from utils import streamtape, doodstream, mixdrop

HOSTS = {"streamtape": streamtape, "doodstream": doodstream, "mixdrop": mixdrop}
LABELS = {"streamtape": "Streamtape", "doodstream": "DoodStream", "mixdrop": "Mixdrop"}


def parse_name(token):
    """'dood', 'doodstream', 'mix', 'mixddrop', 'st' ... -> canonical name, or None."""
    t = token.strip().lower()
    if t.startswith(("stream", "st", "tape")):
        return "streamtape"
    if t.startswith(("dood", "dd")):
        return "doodstream"
    if t.startswith(("mix", "mx")):
        return "mixdrop"
    return None


async def is_on(name):
    """True when the server has its API keys set AND is switched on with /active."""
    if not HOSTS[name].enabled:
        return False
    active = await get_active_hosts()
    return active is None or name in active
