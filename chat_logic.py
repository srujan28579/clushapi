# chat_logic.py
from flask import request
from flask_socketio import join_room, leave_room, emit
import database

def register_chat_events(socketio, verify_match_callback=None):
    
    @socketio.on('join_room')
    def on_join(data):
        # We now expect UUIDs for the room logic, but Names for display
        room = data['room']         # e.g., "uuid1_uuid2"
        username = data['username'] # e.g., "Salil"
        
        # 🔒 SECURITY CHECK
        # Extract the two User IDs from the room name
        try:
            user1_id, user2_id = room.split('_')
            
            if verify_match_callback:
                is_valid = verify_match_callback(user1_id, user2_id)
                if not is_valid:
                    print(f"⛔ BLOCKING: {username} tried to join {room} but is not matched.")
                    emit('error', {'message': 'You are not matched with this user!'})
                    return # Stop here
        except:
            print(f"⚠️ Room name format warning: {room}")

        # If valid, let them in
        join_room(room)
        print(f"👥 {username} joined room: {room}")

        # Load History
        history = database.get_chat_history(room)
        emit('load_history', history, room=request.sid)

    @socketio.on('send_message')
    def on_send(data):
        room = data['room']
        sender = data['sender']
        message = data['message']
        
        # 1. Generate Timestamp NOW
        import datetime
        timestamp = datetime.datetime.now().strftime("%I:%M %p") # "10:30 PM"
        
        # 2. Add it to the data we send back
        data['timestamp'] = timestamp
        
        print(f"📩 Saving: {message} at {timestamp}")
        
        # 3. SAVE to Database (Update database.py to accept timestamp if needed, 
        # or let it generate its own, but sending it to UI is key)
        database.save_message(room, sender, message)
        
        # 4. SEND to everyone (now includes 'timestamp')
        emit('receive_message', data, room=room)