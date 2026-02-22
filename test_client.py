# test_client.py
import socketio

# Create a standard Socket.IO client
sio = socketio.Client()

@sio.event
def connect():
    print("✅ CONNECTION SUCCESSFUL!")
    print("   Sending 'Hello' to the server...")
    sio.emit('join_room', {'room': 'global', 'username': 'TesterBot'})
    sio.emit('send_message', {
        'room': 'global', 
        'sender': 'TesterBot', 
        'message': 'Hello from Python!'
    })

@sio.event
def receive_message(data):
    print(f"📩 SERVER REPLIED: {data}")

@sio.event
def disconnect():
    print("❌ Disconnected from server")

if __name__ == '__main__':
    try:
        # CONNECT TO LOCALHOST (Direct connection, no Ngrok)
        print("⏳ Attempting to connect to localhost:10000...")
        sio.connect('http://127.0.0.1:10000')
        sio.wait()
    except Exception as e:
        print(f"🔥 Error: {e}")