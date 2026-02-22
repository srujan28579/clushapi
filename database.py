# database.py (Hybrid: Local Storage for Speed)
import sqlite3
import datetime
import os

DB_NAME = "clush_chat.db"

def init_db():
    """Creates the local database for messages."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Create Messages Table locally
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    print("💾 Local Database (SQLite) Initialized for Messages!")

def save_message(room_id, sender, message):
    """Saves message to local PC file (Instant Speed)."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('INSERT INTO messages (room_id, sender, message, timestamp) VALUES (?, ?, ?, ?)',
                       (room_id, sender, message, timestamp))
        
        conn.commit()
        conn.close()
        print(f"💾 Saved Locally: {message}")
    except Exception as e:
        print(f"❌ Error Saving Local Message: {e}")

def get_chat_history(room_id):
    """Reads history from local PC file."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('SELECT sender, message, timestamp FROM messages WHERE room_id = ? ORDER BY id ASC LIMIT 50', (room_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [{"sender": r[0], "message": r[1], "timestamp": r[2]} for r in rows]
    except Exception as e:
        print(f"❌ Error Reading History: {e}")
        return []