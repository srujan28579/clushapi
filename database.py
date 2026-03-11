import sqlite3
import datetime

DB_NAME = "clush_chat.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL, sender TEXT NOT NULL, message TEXT NOT NULL,
            timestamp TEXT NOT NULL, media_type TEXT, media_url TEXT,
            encryption_key TEXT, encryption_iv TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_message(room_id, sender, message, media_type='text', media_url=None, enc_key=None, enc_iv=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO messages (room_id, sender, message, timestamp, media_type, media_url, encryption_key, encryption_iv) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (room_id, sender, message, timestamp, media_type, media_url, enc_key, enc_iv))
    conn.commit()
    conn.close()
    return timestamp

def get_chat_history(room_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT sender, message, timestamp, media_type, media_url, encryption_key, encryption_iv 
        FROM messages WHERE room_id = ? ORDER BY id ASC LIMIT 50
    ''', (room_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"sender": r[0], "message": r[1], "timestamp": r[2], "media_type": r[3], "media_url": r[4], "encryption_key": r[5], "encryption_iv": r[6]} for r in rows]