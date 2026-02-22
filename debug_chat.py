# debug_chat.py
# ---------------------------------------------------------
# 🕵️‍♂️ DEBUG CHAT TOOL
# Use this to act as the "Other Person" and test your app.
# ---------------------------------------------------------
import socketio

# 1. SETUP
sio = socketio.Client()
server_url = 'http://127.0.0.1:10000' # Make sure this matches your local server

@sio.event
def connect():
    print("✅ CONNECTED to Server!")

@sio.event
def receive_message(data):
    # Print messages from the OTHER person (Your Phone)
    if data.get('sender') != my_name:
        print(f"\n📱 {data.get('sender')}: {data.get('message')}")
        print(f"{my_name}: ", end="", flush=True)

# 2. INPUTS
print("-" * 40)
print("       🕵️‍♂️ CLUSH DEBUG CHATTER")
print("-" * 40)

# We need the EXACT Room ID from your Server Terminal
room_id = input("Paste Room ID (e.g., uuid1_uuid2): ").strip()
my_name = input("Enter Fake Name (e.g., Rahul): ").strip()

# 3. CONNECT & JOIN
try:
    sio.connect(server_url)
    
    # We join the room using the UUIDs, but we use a fake name for display
    sio.emit('join_room', {'room': room_id, 'username': my_name})
    
    print(f"\n🚀 Joined Room: {room_id}")
    print(f"💬 You are now chatting as '{my_name}'")
    print("-" * 40)
    print(f"{my_name}: ", end="", flush=True)

    # 4. CHAT LOOP
    while True:
        msg = input()
        if msg.lower() == 'exit':
            break
        if msg.strip():
            # Send message to the room
            sio.emit('send_message', {
                'room': room_id, 
                'sender': my_name, 
                'message': msg
            })
            # (The server will echo it back, so we don't print it twice here)

except KeyboardInterrupt:
    print("\n👋 Exiting...")
    sio.disconnect()
except Exception as e:
    print(f"\n❌ Error: {e}")