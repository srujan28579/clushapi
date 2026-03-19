# server.py
import os
import cv2
import face_recognition
import datetime
import requests
import numpy as np
import traceback
from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from supabase import create_client, Client

import chat_logic
import database
import moderation_logic

SUPABASE_URL = "https://roblwklgvyvjrgvyumqp.supabase.co/"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJvYmx3a2xndnl2anJndnl1bXFwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MDM5NjQ5OCwiZXhwIjoyMDg1OTcyNDk4fQ.LZgKHjwngrnvO-lhvOTP2hyE68EiaMcJ9nPEhhlBS5s"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = Flask(__name__)
app.config['SECRET_KEY'] = 'clush_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER): 
    os.makedirs(UPLOAD_FOLDER)

print("🚀 Clush Server Starting (Stateless Cloud + STRICT OCR)...", flush=True)
database.init_db()

@app.route('/moderate_image', methods=['POST'])
def moderate_image():
    print("\n🔍 --- NEW IMAGE MODERATION REQUEST ---", flush=True)
    if 'image' not in request.files:
        return jsonify({"status": "error", "message": "No image uploaded"}), 400
        
    image_bytes = request.files['image'].read()
    
    if moderation_logic.check_image_for_text(image_bytes):
        print("🚨 REJECTED: Image contains prohibited text/IDs.", flush=True)
        return jsonify({"status": "rejected", "message": "Images containing handles or contact info are strictly prohibited."}), 200
    
    print("✅ APPROVED: Image is clean.", flush=True)
    return jsonify({"status": "approved"}), 200


@app.route('/verify', methods=['POST'])      
def verify_face():
    print("\n📥 --- NEW VIDEO VERIFICATION REQUEST ---", flush=True)
    user_id = request.form.get('user_id')
    video_file = request.files.get('video')

    if not user_id or not video_file: 
        return jsonify({"match": False, "score": 0.0, "error": "Missing data"}), 400

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = os.path.join(UPLOAD_FOLDER, f"video_{user_id}_{timestamp}.mp4")
    
    try:
        # 1. Download the profile picture
        user_data = supabase.table('profiles').select('photo_urls').eq('id', user_id).execute()
        if not user_data.data or not user_data.data[0].get('photo_urls'): 
            return jsonify({"match": False, "score": 0.0, "error": "No profile photos"}), 404

        profile_url = user_data.data[0]['photo_urls'][0] 
        response = requests.get(profile_url)
        
        # 2. Convert straight to OpenCV image in memory
        image_array = np.frombuffer(response.content, np.uint8)
        raw_profile = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if raw_profile is None:
            return jsonify({"match": False, "score": 0.0, "error": "Corrupted profile picture format."}), 400

        # Resize to prevent RAM overload
        p_height, p_width = raw_profile.shape[:2]
        if p_width > 600:
            raw_profile = cv2.resize(raw_profile, (600, int((600 / p_width) * p_height)))
            
        rgb_profile = cv2.cvtColor(raw_profile, cv2.COLOR_BGR2RGB)
        saved_profile_img = np.ascontiguousarray(rgb_profile, dtype=np.uint8)
        
        # 3. Save the live video temporarily to disk so OpenCV can read it
        video_file.save(video_path)

        cap = cv2.VideoCapture(video_path)
        for _ in range(15): cap.read() # Skip focus frames
        success, frame = cap.read()
        cap.release()

        if not success: 
            return jsonify({"match": False, "score": 0.0, "error": "Invalid video or video too short"}), 400

        # Resize and format the video frame
        height, width = frame.shape[:2]
        small_frame = cv2.resize(frame, (500, int((500 / width) * height)))
        rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        rgb_frame = np.ascontiguousarray(rgb_frame, dtype=np.uint8)

        # 4. Map the faces
        print("👤 Mapping faces...", flush=True)
        profile_locations = face_recognition.face_locations(saved_profile_img, number_of_times_to_upsample=1)
        if not profile_locations:
            return jsonify({"match": False, "score": 0.0, "error": "No face detected in profile picture"}), 200
        profile_encodings = face_recognition.face_encodings(saved_profile_img, known_face_locations=profile_locations)
        
        live_locations = face_recognition.face_locations(rgb_frame, number_of_times_to_upsample=1)
        if not live_locations:
            return jsonify({"match": False, "score": 0.0, "error": "No face detected in live video"}), 200
        live_encodings = face_recognition.face_encodings(rgb_frame, known_face_locations=live_locations)

        # 5. Compare mathematically
        distance = face_recognition.face_distance([profile_encodings[0]], live_encodings[0])[0]
        score = round((1 - distance) * 100, 2)
        is_match = bool(distance <= 0.5)
        
        print(f"✅ VERIFICATION COMPLETE: Match={is_match}, Score={score}%", flush=True)
        return jsonify({"match": is_match, "score": score})

    except Exception as e:
        print("\n❌ --- CRASH REPORT ---", flush=True)
        traceback.print_exc()
        print("----------------------\n", flush=True)
        return jsonify({"match": False, "score": 0.0, "error": str(e)}), 500

    finally:
        # 🧹 THE VACUUM CLEANER: Deletes the temp video so your server stays fast and empty
        if os.path.exists(video_path):
            try:
                os.remove(video_path)
                print("🧹 Cleaned up temporary video file.", flush=True)
            except Exception as e:
                print(f"⚠️ Could not delete temp file: {e}", flush=True)


def verify_supabase_match(user1_id, user2_id):
    try:
        response = supabase.table('matches').select('*').or_(
            f"and(user_a.eq.{user1_id},user_b.eq.{user2_id}),and(user_a.eq.{user2_id},user_b.eq.{user1_id})"
        ).execute()
        return len(response.data) > 0
    except Exception: 
        return False

chat_logic.register_chat_events(socketio, verify_match_callback=verify_supabase_match)

if __name__ == '__main__':
    print("✅ Clush Server Ready (Port 10000)", flush=True)
    socketio.run(app, host='0.0.0.0', port=10000)