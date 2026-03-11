# server.py
import os
import cv2
import face_recognition
import datetime
import requests
import numpy as np
from PIL import Image, ImageOps
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
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

print("🚀 Clush Server Starting (Vision + Chat + STRICT Zero-Text Moderation)...", flush=True)
database.init_db() 

@app.route('/moderate_image', methods=['POST'])
def moderate_image():
    print("\n🔍 --- NEW IMAGE MODERATION REQUEST ---", flush=True)
    if 'image' not in request.files:
        return jsonify({"status": "error", "message": "No image uploaded"}), 400
        
    image_bytes = request.files['image'].read()
    print("⚙️ Running OCR scan on image...", flush=True)
    
    if moderation_logic.check_image_for_text(image_bytes):
        print("🚨 REJECTED: Image contains text overlay.", flush=True)
        return jsonify({"status": "rejected", "message": "Images containing any text overlays are strictly prohibited."}), 200
    
    print("✅ APPROVED: Image is clean.", flush=True)
    return jsonify({"status": "approved"}), 200

@app.route('/verify', methods=['POST'])      
def verify_face():
    print("\n📥 --- NEW VIDEO VERIFICATION REQUEST ---", flush=True)
    user_id = request.form.get('user_id')
    video_file = request.files.get('video')

    if not user_id or not video_file: return jsonify({"match": False, "score": 0.0, "error": "Missing data"}), 400

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        user_data = supabase.table('profiles').select('photo_urls').eq('id', user_id).execute()
        if not user_data.data or not user_data.data[0].get('photo_urls'): return jsonify({"match": False, "score": 0.0, "error": "No profile photos"}), 404

        profile_url = user_data.data[0]['photo_urls'][0] 
        response = requests.get(profile_url, stream=True)
        
        profile_path = os.path.join(UPLOAD_FOLDER, f"profile_{user_id}_{timestamp}.jpg")
        with open(profile_path, 'wb') as f: f.write(response.content)
        
        video_path = os.path.join(UPLOAD_FOLDER, f"video_{user_id}_{timestamp}.mp4")
        video_file.save(video_path)

        cap = cv2.VideoCapture(video_path)
        for _ in range(15): cap.read()
        success, frame = cap.read()
        cap.release()

        if not success: return jsonify({"match": False, "score": 0.0, "error": "Invalid video"}), 400

        height, width = frame.shape[:2]
        small_frame = cv2.resize(frame, (500, int((500 / width) * height)))
        rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        pil_img = ImageOps.exif_transpose(Image.open(profile_path)).convert('RGB')
        saved_profile_img = np.array(pil_img)

        profile_locations = face_recognition.face_locations(saved_profile_img, number_of_times_to_upsample=2)
        profile_encodings = face_recognition.face_encodings(saved_profile_img, known_face_locations=profile_locations)
        live_locations = face_recognition.face_locations(rgb_frame, number_of_times_to_upsample=2)
        live_encodings = face_recognition.face_encodings(rgb_frame, known_face_locations=live_locations)

        if not profile_encodings or not live_encodings: return jsonify({"match": False, "score": 0.0, "error": "Face not detected"}), 200

        distance = face_recognition.face_distance([profile_encodings[0]], live_encodings[0])[0]
        score = round((1 - distance) * 100, 2)
        return jsonify({"match": bool(distance <= 0.5), "score": score})

    except Exception as e:
        return jsonify({"match": False, "score": 0.0, "error": str(e)}), 500

def verify_supabase_match(user1_id, user2_id):
    try:
        response = supabase.table('matches').select('*').or_(
            f"and(user_a.eq.{user1_id},user_b.eq.{user2_id}),and(user_a.eq.{user2_id},user_b.eq.{user1_id})"
        ).execute()
        return len(response.data) > 0
    except Exception: return False

chat_logic.register_chat_events(socketio, verify_match_callback=verify_supabase_match)

if __name__ == '__main__':
    print("✅ Clush Server Ready (Port 10000)", flush=True)
    socketio.run(app, host='0.0.0.0', port=10000)