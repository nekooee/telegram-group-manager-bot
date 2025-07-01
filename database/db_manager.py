import aiosqlite
from config import DB_PATH

async def init_db():
    """Initial setup for the database"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                delete_at TEXT NOT NULL,
                handler_name TEXT DEFAULT 'del_after_24'
            )
        """)
        await db.commit()

async def save_message_for_deletion(chat_id: int, message_id: int, delete_at: str, handler_name: str = 'del_after_24'):
    """Save a message for later deletion"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (chat_id, message_id, delete_at, handler_name) VALUES (?, ?, ?, ?)",
            (chat_id, message_id, delete_at, handler_name),
        )
        await db.commit()

async def get_expired_messages(current_time: str):
    """Retrieve messages that are expired"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, chat_id, message_id FROM messages WHERE delete_at <= ?",
            (current_time,)
        ) as cursor:
            return await cursor.fetchall()

async def delete_message_record(message_record_id: int):
    """Delete a message record from the database"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE id = ?", (message_record_id,))
        await db.commit()
