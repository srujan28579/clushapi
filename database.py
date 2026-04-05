# database.py
import os
import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

def init_db():
    print("☁️ Connected to Supabase for Chat Storage.", flush=True)

def save_message(room_id, sender, message, media_type='text', media_url=None, enc_key=None, enc_iv=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        supabase.table('messages').insert({
            "room_id": room_id,
            "sender": sender,
            "message": message,
            "timestamp": timestamp,
            "media_type": media_type,
            "media_url": media_url,
            "encryption_key": enc_key,
            "encryption_iv": enc_iv,
        }).execute()
    except Exception as e:
        print(f"❌ Supabase Insert Error: {e}", flush=True)
    return timestamp

def get_chat_history(room_id):
    print(f"📥 Fetching chat history for room: {room_id}...", flush=True)
    try:
        response = supabase.table('messages').select('*').eq('room_id', room_id).order('id', desc=False).limit(50).execute()
        if not response.data:
            print("⚠️ No messages found.", flush=True)
            return []
        print(f"✅ Found {len(response.data)} messages.", flush=True)
        return [{
            "sender":         row.get('sender', ''),
            "message":        row.get('message', ''),
            "timestamp":      row.get('timestamp', ''),
            "media_type":     row.get('media_type') or 'text',
            "media_url":      row.get('media_url') or '',
            "encryption_key": row.get('encryption_key') or '',
            "encryption_iv":  row.get('encryption_iv') or '',
        } for row in response.data]
    except Exception as e:
        print(f"❌ Supabase Fetch Error: {e}", flush=True)
        return []
