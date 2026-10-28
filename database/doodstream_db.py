import time
import motor.motor_asyncio
from config import DATABASE_URI

_client = motor.motor_asyncio.AsyncIOMotorClient(DATABASE_URI)
_db = _client["FileToLinkBot"]
col = _db.doodstream

# One row per bot file (file_id = message id in BIN_CHANNEL):
#   st_id   : current DoodStream file code
#   name    : file name used on DoodStream (kept the same on every restore)
#   status  : uploading | ok | failed
#   healed  : how many times the file was restored
#   fails   : failed upload attempts in a row


async def get(file_id):
    return await col.find_one({"file_id": int(file_id)})


async def upsert(file_id, **fields):
    fields["updated"] = time.time()
    await col.update_one({"file_id": int(file_id)}, {"$set": fields}, upsert=True)


async def inc(file_id, **counters):
    await col.update_one({"file_id": int(file_id)}, {"$inc": counters})


async def all_records():
    return await col.find({}).to_list(length=None)
