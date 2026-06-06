import database

def register_chat_events(sio, supabase):

    @sio.on('join_room')
    async def handle_join(sid, data):
        room = data.get('room')
        username = data.get('username')
        users = room.split('_')
        if len(users) == 2:
            import asyncio
            is_match = await asyncio.to_thread(
                lambda: _verify_match(supabase, users[0], users[1])
            )
            if is_match:
                await sio.enter_room(sid, room)
                print(f"🟢 {username} joined room {room}", flush=True)
                history = await asyncio.to_thread(database.get_chat_history, room)
                await sio.emit('chat_history', history, to=sid)

    @sio.on('send_message')
    async def handle_message(sid, data):
        room = data.get('room')
        sender = data.get('sender')
        message = data.get('message')
        media_type = data.get('media_type', 'text')
        media_url = data.get('media_url')
        enc_key = data.get('encryption_key')
        enc_iv = data.get('encryption_iv')

        import asyncio
        timestamp = await asyncio.to_thread(
            database.save_message, room, sender, message, media_type, media_url, enc_key, enc_iv
        )
        await sio.emit('receive_message', {
            'sender': sender,
            'message': message,
            'timestamp': timestamp,
            'media_type': media_type,
            'media_url': media_url,
            'encryption_key': enc_key,
            'encryption_iv': enc_iv,
        }, room=room)

    @sio.on('leave_room')
    async def handle_leave(sid, data):
        await sio.leave_room(sid, data.get('room'))


def _verify_match(supabase, user1_id, user2_id):
    try:
        response = supabase.table('matches').select('*').or_(
            f"and(user_a.eq.{user1_id},user_b.eq.{user2_id}),and(user_a.eq.{user2_id},user_b.eq.{user1_id})"
        ).execute()
        return len(response.data) > 0
    except Exception:
        return False
