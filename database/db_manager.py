import aiosqlite
from config import DB_PATH
from datetime import datetime, timezone

async def init_db():
    """Initial setup for the database"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                username TEXT,
                delete_at TEXT NOT NULL,
                handler_name TEXT DEFAULT 'del_after_24',
                created_at TEXT,
                error_message TEXT
            )
        """)
        await db.commit()

async def save_message_for_deletion(chat_id: int, message_id: int, delete_at: str, handler_name: str = 'del_after_24', username: str = None):
    """Save a message for later deletion (always replaces any existing schedule)."""
    await upsert_message_for_deletion(chat_id, message_id, delete_at, handler_name, username)


async def upsert_message_for_deletion(
    chat_id: int,
    message_id: int,
    delete_at: str,
    handler_name: str = 'del_after_24',
    username: str = None,
):
    """Replace any existing deletion schedule for this message with a new one."""
    created_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM messages WHERE chat_id = ? AND message_id = ?",
            (chat_id, message_id),
        )
        await db.execute(
            "INSERT INTO messages (chat_id, message_id, username, delete_at, handler_name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, message_id, username, delete_at, handler_name, created_at),
        )
        await db.commit()


async def get_pending_deletion(chat_id: int, message_id: int):
    """Return the pending deletion record for a message, if any."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT id, chat_id, message_id, username, delete_at, handler_name, created_at, error_message
            FROM messages
            WHERE chat_id = ? AND message_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id, message_id),
        ) as cursor:
            return await cursor.fetchone()


async def cancel_pending_deletion(chat_id: int, message_id: int) -> bool:
    """Remove pending deletion schedule so the message will not be auto-deleted."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM messages WHERE chat_id = ? AND message_id = ?",
            (chat_id, message_id),
        )
        await db.commit()
        return cursor.rowcount > 0

async def get_expired_messages(current_time: str):
    """Retrieve messages that are expired"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, chat_id, message_id, username, error_message FROM messages WHERE delete_at <= ?",
            (current_time,)
        ) as cursor:
            return await cursor.fetchall()

async def delete_message_record(message_record_id: int):
    """Delete a message record from the database"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM messages WHERE id = ?", (message_record_id,))
        await db.commit()

async def update_message_error(message_record_id: int, error_message: str):
    """Update message record with error information"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE messages SET error_message = ? WHERE id = ?",
            (error_message, message_record_id)
        )
        await db.commit()

async def get_all_pending_messages():
    """Get all pending messages for report"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, chat_id, message_id, username, delete_at, handler_name, created_at, error_message FROM messages ORDER BY delete_at"
        ) as cursor:
            return await cursor.fetchall()