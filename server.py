# server.py (Vision Booster + EXIF Fix + Chat)
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

# --- 1. CONFIGURATION ---
SUPABASE_URL = "https://roblwklgvyvjrgvyumqp.supabase.co/"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJvYmx3a2xndnl2anJndnl1bXFwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MDM5NjQ5OCwiZXhwIjoyMDg1OTcyNDk4fQ.LZgKHjwngrnvO-lhvOTP2hyE68EiaMcJ9nPEhhlBS5s" # ⚠️ Put your key here

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'clush_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

print("🚀 Clush Server Starting (Vision Booster Edition)...", flush=True)
database.init_db() 

# --- 3. ENDPOINT: VIDEO FACE VERIFICATION 🎥 ---
@app.route('/verify', methods=['POST'])      
def verify_face():
    print("\n📥 --- NEW VIDEO VERIFICATION REQUEST ---", flush=True)
    
    user_id = request.form.get('user_id')
    video_file = request.files.get('video')

    if not user_id or not video_file:
        print("❌ ERROR: Missing User ID or Video file.", flush=True)
        return jsonify({"match": False, "score": 0.0, "error": "Missing data"}), 400

    print(f"👤 User ID: {user_id}", flush=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        # =========================================================
        # 1. FETCH PROFILE IMAGE
        # =========================================================
        print("🔄 Fetching Profile Image directly from Supabase...", flush=True)
        user_data = supabase.table('profiles').select('photo_urls').eq('id', user_id).execute()
        
        if not user_data.data:
            return jsonify({"match": False, "score": 0.0, "error": "User not found"}), 404
            
        photo_urls = user_data.data[0].get('photo_urls', [])
        if not photo_urls or len(photo_urls) == 0:
            return jsonify({"match": False, "score": 0.0, "error": "No profile photos found"}), 404

        profile_url = photo_urls[0] 
        print(f"🔗 Downloading Profile Pic...", flush=True)
        response = requests.get(profile_url, stream=True)
        
        profile_path = os.path.join(UPLOAD_FOLDER, f"profile_{user_id}_{timestamp}.jpg")
        with open(profile_path, 'wb') as f:
            f.write(response.content)
        
        video_path = os.path.join(UPLOAD_FOLDER, f"video_{user_id}_{timestamp}.mp4")
        video_file.save(video_path)
        print("💾 Saved Profile & Video.", flush=True)

        # =========================================================
        # 2. PROCESS VIDEO FRAME
        # =========================================================
        cap = cv2.VideoCapture(video_path)
        for _ in range(15):  # Skip first 15 frames
            cap.read()
            
        success, frame = cap.read()
        cap.release()

        if not success:
            return jsonify({"match": False, "score": 0.0, "error": "Invalid video"}), 400

        # Resize video frame
        height, width = frame.shape[:2]
        new_width = 500
        new_height = int((new_width / width) * height)
        small_frame = cv2.resize(frame, (new_width, new_height))
        rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        # =========================================================
        # 3. COMPARE FACES (BOOSTED VISION) 👓
        # =========================================================
        print("🧠 AI is processing faces (Boosted Vision)...", flush=True)
        
        # FIX: Force the profile image to be upright using PIL EXIF transpose
        pil_img = Image.open(profile_path)
        pil_img = ImageOps.exif_transpose(pil_img) # <-- This fixes smartphone rotation!
        pil_img = pil_img.convert('RGB')
        saved_profile_img = np.array(pil_img)

        # Tell AI to scan harder (upsample=2)
        profile_locations = face_recognition.face_locations(saved_profile_img, number_of_times_to_upsample=2)
        profile_encodings = face_recognition.face_encodings(saved_profile_img, known_face_locations=profile_locations)
        
        live_locations = face_recognition.face_locations(rgb_frame, number_of_times_to_upsample=2)
        live_encodings = face_recognition.face_encodings(rgb_frame, known_face_locations=live_locations)

        if not profile_encodings:
            print("⚠️ WARNING: Still no face detected in the Profile Picture.", flush=True)
            return jsonify({"match": False, "score": 0.0, "error": "No face in profile pic"}), 200
            
        if not live_encodings:
            print("⚠️ WARNING: No face detected in the Video Frame.", flush=True)
            return jsonify({"match": False, "score": 0.0, "error": "No face found in video"}), 200

        # Calculate Score
        distance = face_recognition.face_distance([profile_encodings[0]], live_encodings[0])[0]
        score = round((1 - distance) * 100, 2)
        is_match = distance <= 0.5 

        print(f"📊 Match Score: {score}% (Distance: {round(distance, 4)})", flush=True)

        response_data = {"match": bool(is_match), "score": score}
        print(f"📤 Sending to App: {response_data}", flush=True)
            
        return jsonify(response_data)

    except Exception as e:
        print(f"❌ Verification Logic Error: {e}", flush=True)
        return jsonify({"match": False, "score": 0.0, "error": str(e)}), 500


# --- 4. CHAT MATCH VERIFICATION ---
def verify_supabase_match(user1_id, user2_id):
    try:
        response = supabase.table('matches').select('*').or_(
            f"and(user_a.eq.{user1_id},user_b.eq.{user2_id}),"
            f"and(user_a.eq.{user2_id},user_b.eq.{user1_id})"
        ).execute()
        return len(response.data) > 0
    except Exception as e:
        return False

chat_logic.register_chat_events(socketio, verify_match_callback=verify_supabase_match)

if __name__ == '__main__':
    print("✅ Clush Server Ready (Port 10000)", flush=True)
    socketio.run(app, host='0.0.0.0', port=10000)