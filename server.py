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
            print("❌ No face encodings extracted from profile photos", flush=True)
            return jsonify({"match": False, "score": 0.0, "error": "No face detected in any profile picture"}), 200
        print(f"✅ Got {len(profile_encodings)} profile encoding(s)", flush=True)

        # 3. Extract multiple frames spread across the video
        video_file.save(video_path)
        cap = cv2.VideoCapture(video_path)

        opened = cap.isOpened()
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        codec = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec_str = "".join([chr((codec >> 8 * i) & 0xFF) for i in range(4)])
        print(f"🎥 Video opened={opened}, codec={codec_str}, {total_frames} frames @ {fps:.1f}fps", flush=True)

        if not opened:
            cap.release()
            print("❌ OpenCV could not open the video file", flush=True)
            return jsonify({"match": False, "score": 0.0, "error": "Could not read video file — unsupported format"}), 400

        # Try reading first frame immediately to verify codec works
        success, test_frame = cap.read()
        if not success or test_frame is None:
            cap.release()
            print("❌ OpenCV opened file but could not decode frames — likely unsupported codec", flush=True)
            return jsonify({"match": False, "score": 0.0, "error": "Video codec not supported"}), 400
        print(f"🖼️ First frame: {test_frame.shape}, brightness={test_frame.mean():.1f}", flush=True)

        # Save first frame for inspection
        debug_frame_path = os.path.join(UPLOAD_FOLDER, f"debug_frame_{user_id}.jpg")
        cv2.imwrite(debug_frame_path, test_frame)
        print(f"💾 Debug frame saved to {debug_frame_path}", flush=True)

        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # reset to start

        # Skip first ~1 second (camera focus), then sample 10 frames spread across remainder
        skip = int(fps)
        usable = total_frames - skip
        if usable < 1:
            # video is short — just use all frames including the first second
            skip = 0
            usable = total_frames
            print("⚠️ Video short — sampling from beginning", flush=True)

        sample_count = min(10, usable)
        sample_positions = [skip + int(i * usable / sample_count) for i in range(sample_count)]
        print(f"📍 Sampling frames at positions: {sample_positions}", flush=True)

        live_encodings = []
        nose_offsets = []  # track nose position relative to eyes across frames

        for pos in sample_positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            success, frame = cap.read()
            if not success:
                print(f"  ⚠️ Frame {pos}: read failed", flush=True)
                continue
            print(f"  Frame {pos}: shape={frame.shape}, brightness={frame.mean():.1f}", flush=True)
            h, w = frame.shape[:2]
            if w > 800:
                frame = cv2.resize(frame, (800, int((800 / w) * h)))

            # Try all 4 rotations — Flutter portrait videos sometimes arrive rotated
            rotations = [frame,
                         cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE),
                         cv2.rotate(frame, cv2.ROTATE_180),
                         cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)]
            locs = []
            rgb_frame = None
            for rot in rotations:
                candidate = np.ascontiguousarray(cv2.cvtColor(rot, cv2.COLOR_BGR2RGB), dtype=np.uint8)
                locs = face_recognition.face_locations(candidate, number_of_times_to_upsample=2)
                if locs:
                    rgb_frame = candidate
                    break

            if not locs or rgb_frame is None:
                print(f"  ⚠️ Frame {pos}: no face found in any rotation", flush=True)
                continue

            print(f"  ✅ Frame {pos}: {len(locs)} face(s) detected", flush=True)
            encs = face_recognition.face_encodings(rgb_frame, known_face_locations=locs, num_jitters=1)
            live_encodings.extend(encs)

            # Liveness: extract nose offset to detect head turn
            if locs:
                landmarks_list = face_recognition.face_landmarks(rgb_frame, face_locations=locs)
                for landmarks in landmarks_list:
                    nose_tip = landmarks.get('nose_tip', [])
                    left_eye = landmarks.get('left_eye', [])
                    right_eye = landmarks.get('right_eye', [])
                    if nose_tip and left_eye and right_eye:
                        nose_x = nose_tip[len(nose_tip) // 2][0]
                        eye_center_x = (
                            sum(p[0] for p in left_eye) / len(left_eye) +
                            sum(p[0] for p in right_eye) / len(right_eye)
                        ) / 2
                        eye_width = abs(
                            sum(p[0] for p in right_eye) / len(right_eye) -
                            sum(p[0] for p in left_eye) / len(left_eye)
                        )
                        # Normalize offset by eye width so it's scale-independent
                        if eye_width > 0:
                            nose_offsets.append((nose_x - eye_center_x) / eye_width)

        cap.release()

        print(f"🎞️ Sampled {len(sample_positions)} frames, got {len(live_encodings)} face encoding(s), {len(nose_offsets)} nose offset(s)", flush=True)
        if not live_encodings:
            print("❌ No face detected in any video frame", flush=True)
            return jsonify({"match": False, "score": 0.0, "error": "No face detected in live video"}), 200

        # 4. Verify head turn actually happened
        head_turned = False
        if len(nose_offsets) >= 3:
            offset_range = max(nose_offsets) - min(nose_offsets)
            # A real head turn shifts the nose offset by at least 0.3x the eye width
            head_turned = offset_range >= 0.3
            print(f"🔄 Head turn check: range={offset_range:.3f}, passed={head_turned}", flush=True)

        if not head_turned:
            print("🚫 REJECTED: No head turn detected — possible photo spoof.", flush=True)
            return jsonify({"match": False, "score": 0.0, "error": "Liveness check failed — please turn your head as instructed"}), 200

        # 5. Compare every live encoding against every profile encoding — take best match
        print(f"🔬 Comparing {len(live_encodings)} live frame(s) vs {len(profile_encodings)} profile encoding(s)...", flush=True)
        best_distance = min(
            face_recognition.face_distance([p_enc], l_enc)[0]
            for p_enc in profile_encodings
            for l_enc in live_encodings
        )

        score = round((1 - best_distance) * 100, 2)
        is_match = bool(best_distance <= 0.45)

        print(f"✅ VERIFICATION COMPLETE: Match={is_match}, Score={score}%, Distance={best_distance:.4f}, Threshold=0.45", flush=True)
        print(f"📊 Raw distances: {sorted([round(face_recognition.face_distance([p], l)[0], 4) for p in profile_encodings for l in live_encodings])}", flush=True)
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