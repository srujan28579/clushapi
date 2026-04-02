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
from flasgger import Swagger
from supabase import create_client, Client
from dotenv import load_dotenv

import chat_logic
import database
import moderation_logic

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY in environment")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = Flask(__name__)
app.config['SECRET_KEY'] = 'clush_secret_key'
app.config['SWAGGER'] = {'title': 'Clush API', 'uiversion': 3}
Swagger(app)
socketio = SocketIO(app, cors_allowed_origins="*")

UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER): 
    os.makedirs(UPLOAD_FOLDER)

print("🚀 Clush Server Starting (Stateless Cloud + STRICT OCR)...", flush=True)
database.init_db()

@app.route('/moderate_image', methods=['POST'])
def moderate_image():
    """
    Moderate an image for prohibited text or contact info.
    ---
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: image
        type: file
        required: true
        description: The image file to moderate
    responses:
      200:
        description: Moderation result (approved or rejected)
        schema:
          type: object
          properties:
            status:
              type: string
              example: approved
            message:
              type: string
      400:
        description: No image uploaded
    """
    print("\n🔍 --- NEW IMAGE MODERATION REQUEST ---", flush=True)
    if 'image' not in request.files:
        return jsonify({"status": "error", "message": "No image uploaded"}), 400
        
    image_bytes = request.files['image'].read()
    
    if moderation_logic.check_image_for_nudity(image_bytes):
        print("🚨 REJECTED: Image contains nudity/NSFW content.", flush=True)
        return jsonify({"status": "rejected", "message": "Nudity and explicit content are strictly prohibited."}), 200

    if moderation_logic.check_image_for_text(image_bytes):
        print("🚨 REJECTED: Image contains prohibited text/IDs.", flush=True)
        return jsonify({"status": "rejected", "message": "Images containing handles or contact info are strictly prohibited."}), 200
    
    print("✅ APPROVED: Image is clean.", flush=True)
    return jsonify({"status": "approved"}), 200


@app.route('/verify', methods=['POST'])
def verify_face():
    """
    Verify a user's face against their profile picture.
    ---
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: user_id
        type: string
        required: true
        description: The Supabase user ID
      - in: formData
        name: video
        type: file
        required: true
        description: A short video of the user's face
    responses:
      200:
        description: Verification result
        schema:
          type: object
          properties:
            match:
              type: boolean
              example: true
            score:
              type: number
              example: 87.45
      400:
        description: Missing data or invalid video
      404:
        description: No profile photos found
      500:
        description: Internal server error
    """
    print("\n📥 --- NEW VIDEO VERIFICATION REQUEST ---", flush=True)
    user_id = request.form.get('user_id')
    video_file = request.files.get('video')

    if not user_id or not video_file:
        return jsonify({"match": False, "score": 0.0, "error": "Missing data"}), 400

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = os.path.join(UPLOAD_FOLDER, f"video_{user_id}_{timestamp}.mp4")

    try:
        # 1. Fetch all profile photos
        user_data = supabase.table('profiles').select('photo_urls').eq('id', user_id).execute()
        if not user_data.data or not user_data.data[0].get('photo_urls'):
            return jsonify({"match": False, "score": 0.0, "error": "No profile photos"}), 404

        photo_urls = user_data.data[0]['photo_urls'][:2]  # only first two photos

        # 2. Build encodings from first two profile photos
        print(f"👤 Loading {len(photo_urls)} profile photo(s)...", flush=True)
        profile_encodings = []
        for url in photo_urls:
            try:
                resp = requests.get(url, timeout=10)
                img_array = np.frombuffer(resp.content, np.uint8)
                raw = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if raw is None:
                    continue
                p_h, p_w = raw.shape[:2]
                if p_w > 800:
                    raw = cv2.resize(raw, (800, int((800 / p_w) * p_h)))
                rgb = np.ascontiguousarray(cv2.cvtColor(raw, cv2.COLOR_BGR2RGB), dtype=np.uint8)
                locs = face_recognition.face_locations(rgb, number_of_times_to_upsample=2)
                encs = face_recognition.face_encodings(rgb, known_face_locations=locs, num_jitters=2)
                profile_encodings.extend(encs)
            except Exception as e:
                print(f"⚠️ Skipping photo: {e}", flush=True)

        if not profile_encodings:
            return jsonify({"match": False, "score": 0.0, "error": "No face detected in any profile picture"}), 200

        # 3. Extract multiple frames spread across the video
        video_file.save(video_path)
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30

        # Skip first ~1 second (camera focus), then sample 6 frames spread across remainder
        skip = int(fps)
        usable = total_frames - skip
        if usable < 1:
            cap.release()
            return jsonify({"match": False, "score": 0.0, "error": "Video too short"}), 400

        sample_count = min(6, usable)
        sample_positions = [skip + int(i * usable / sample_count) for i in range(sample_count)]

        live_encodings = []
        for pos in sample_positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            success, frame = cap.read()
            if not success:
                continue
            h, w = frame.shape[:2]
            if w > 600:
                frame = cv2.resize(frame, (600, int((600 / w) * h)))
            rgb_frame = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), dtype=np.uint8)
            locs = face_recognition.face_locations(rgb_frame, number_of_times_to_upsample=1)
            encs = face_recognition.face_encodings(rgb_frame, known_face_locations=locs, num_jitters=1)
            live_encodings.extend(encs)
        cap.release()

        if not live_encodings:
            return jsonify({"match": False, "score": 0.0, "error": "No face detected in live video"}), 200

        # 4. Compare every live encoding against every profile encoding — take best match
        print(f"🔬 Comparing {len(live_encodings)} live frame(s) vs {len(profile_encodings)} profile encoding(s)...", flush=True)
        best_distance = min(
            face_recognition.face_distance([p_enc], l_enc)[0]
            for p_enc in profile_encodings
            for l_enc in live_encodings
        )

        score = round((1 - best_distance) * 100, 2)
        is_match = bool(best_distance <= 0.45)  # slightly stricter threshold

        print(f"✅ VERIFICATION COMPLETE: Match={is_match}, Score={score}%, Distance={best_distance:.4f}", flush=True)
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