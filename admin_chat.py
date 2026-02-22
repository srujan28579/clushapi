import socketio
import sys

# --- CONFIGURATION ---
MY_NAME = "Rex"  # Your Admin Username
# ---------------------

sio = socketio.Client()
server_url = 'http://127.0.0.1:10000'

@sio.event
def connect():
    print(f"✅ CONNECTED as {MY_NAME}!")

@sio.event
def receive_message(data):
    if data['sender'] != MY_NAME:
        print(f"\n📲 {data['sender']}: {data['message']}")
        print("You: ", end="", flush=True)

# 1. Ask who to chat with
target_user = input(f"👤 Who do you want to chat with? (e.g., Rahul): ").strip()

# 2. THE FIX: Alphabetical Sorting (Matches Flutter Logic)
users = [MY_NAME, target_user]
users.sort()  # ['Salil', 'Rahul'] -> ['Rahul', 'Salil']
room_name = f"{users[0]}_{users[1]}"

print(f"🔐 Joining Room: {room_name}")

# 3. Connect & Join
try:
    sio.connect(server_url)
    sio.emit('join_room', {'room': room_name, 'username': MY_NAME})
    
    print("-" * 30)
    print(f"💬 Chatting with {target_user}. Type 'exit' to quit.")
    print("-" * 30)

    while True:
        msg = input("You: ")
        if msg.lower() == 'exit':
            break
        if msg.strip():
            sio.emit('send_message', {
                'room': room_name, 
                'sender': MY_NAME, 
                'message': msg
            })
            # Note: The server sends the message back to the room, 
            # so you might see it twice if we don't filter it in receive_message
            
except KeyboardInterrupt:
    print("\nBye!")
    sio.disconnect()
except Exception as e:
    print(f"❌ Error: {e}")