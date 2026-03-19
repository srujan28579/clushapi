# database.py
import datetime
from supabase import create_client, Client

SUPABASE_URL = "https://roblwklgvyvjrgvyumqp.supabase.co/"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJvYmx3a2xndnl2anJndnl1bXFwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MDM5NjQ5OCwiZXhwIjoyMDg1OTcyNDk4fQ.LZgKHjwngrnvO-lhvOTP2hyE68EiaMcJ9nPEhhlBS5s"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def init_db():
    # No more local files!
    print("☁️ Connected to Supabase for Chat Storage.", flush=True)

def save_message(room_id, sender, message, media_type='text', media_url=None, enc_key=None, enc_iv=None):
    """Saves a new message directly to the Supabase cloud."""
    # Generating timestamp exactly like your original SQLite code
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        data = {
            "room_id": room_id,
            "sender": sender,
            "message": message,
            "timestamp": timestamp,
            "media_type": media_type,
            "media_url": media_url,
            "encryption_key": enc_key,
            "encryption_iv": enc_iv
        }
        supabase.table('messages').insert(data).execute()
        return timestamp
        
    except Exception as e:
        print(f"❌ Supabase Insert Error: {e}", flush=True)
        return timestamp

def get_chat_history(room_id):
    """Fetches the last 50 messages and scrubs NULLs for Flutter."""
    print(f"📥 Fetching chat history for room: {room_id}...", flush=True)
    try:
        response = supabase.table('messages').select('*').eq('room_id', room_id).order('id', desc=False).limit(50).execute()
        
        if response.data:
            print(f"✅ Found {len(response.data)} messages! Scrubbing NULLs for Flutter...", flush=True)
            
            clean_history = []
            for row in response.data:
                clean_history.append({
                    "sender": row.get('sender', ''), 
                    "message": row.get('message', ''), 
                    "timestamp": row.get('timestamp', ''), 
                    # If media_type is null, default to 'text' so Flutter doesn't panic
                    "media_type": row.get('media_type') or 'text', 
                    # If these are null, replace with empty strings
                    "media_url": row.get('media_url') or '', 
                    "encryption_key": row.get('encryption_key') or '', 
                    "encryption_iv": row.get('encryption_iv') or ''
                })
            return clean_history
            
        print("⚠️ No messages found in Supabase for this room.", flush=True)
        return []
        
    except Exception as e:
        print(f"❌ Supabase Fetch Error: {e}", flush=True)
        return []