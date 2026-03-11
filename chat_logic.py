from flask import request
from flask_socketio import join_room, leave_room, emit
import database

def register_chat_events(socketio, verify_match_callback):
    @socketio.on('join_room')
    def handle_join(data):
        room = data.get('room')
        username = data.get('username')
        users = room.split('_')
        if len(users) == 2 and verify_match_callback(users[0], users[1]):
            join_room(room)
            print(f"🟢 {username} joined room {room}")
            emit('chat_history', database.get_chat_history(room), to=request.sid)

    @socketio.on('send_message')
    def handle_message(data):
        room = data.get('room')
        sender = data.get('sender')
        message = data.get('message')
        media_type = data.get('media_type', 'text')
        media_url = data.get('media_url')
        enc_key = data.get('encryption_key')
        enc_iv = data.get('encryption_iv')

        timestamp = database.save_message(room, sender, message, media_type, media_url, enc_key, enc_iv)
        emit('receive_message', {'sender': sender, 'message': message, 'timestamp': timestamp, 'media_type': media_type, 'media_url': media_url, 'encryption_key': enc_key, 'encryption_iv': enc_iv}, room=room)

    @socketio.on('leave_room')
    def handle_leave(data):
        leave_room(data.get('room'))