import time
from database.users_db import db

files_col = db.db.files


async def save_file(file_id, file_name, file_size, mime_type, uploader_id):
    await files_col.update_one(
        {"file_id": file_id},
        {"$set": {
            "file_id": file_id,
            "file_name": file_name,
            "file_size": file_size,
            "mime_type": mime_type,
            "uploader_id": uploader_id,
            "upload_date": time.time()
        }},
        upsert=True
    )


async def get_all_files(limit=300):
    cursor = files_col.find({}).sort("upload_date", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def total_files_count():
    return await files_col.count_documents({})
