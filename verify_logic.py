import os
import cv2
import face_recognition
import datetime
import numpy as np
from flask import request, jsonify

# --- CONFIGURATION ---
EVIDENCE_FOLDER = r'C:\Users\Public\Clush_Evidence'
if not os.path.exists(EVIDENCE_FOLDER):
    os.makedirs(EVIDENCE_FOLDER)

TOLERANCE = 0.45

def _get_profile_encodings(profile_path):
    """Load profile image and return all face encodings from it."""
    img = face_recognition.load_image_file(profile_path)
    h, w = img.shape[:2]
    if w > 800:
        img = cv2.resize(img, (800, int((800 / w) * h)))
        img = np.ascontiguousarray(img)
    locs = face_recognition.face_locations(img, number_of_times_to_upsample=2)
    return face_recognition.face_encodings(img, known_face_locations=locs, num_jitters=2)

def _extract_frames_and_liveness(video_path):
    """
    Sample frames across the video and compute nose offsets for head-turn liveness.
    Returns (live_encodings, nose_offsets).
    """
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    skip = int(fps)  # skip first second (camera focus)
    usable = total_frames - skip
    print(f"🎥 Video: {total_frames} frames @ {fps:.1f}fps, usable={usable}", flush=True)

    if usable < 1:
        cap.release()
        return None, None  # too short

    sample_count = min(10, usable)
    sample_positions = [skip + int(i * usable / sample_count) for i in range(sample_count)]

    live_encodings = []
    nose_offsets = []

    for pos in sample_positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        success, frame = cap.read()
        if not success or frame.mean() < 10:  # skip black frames
            continue
        h, w = frame.shape[:2]
        if w > 600:
            frame = cv2.resize(frame, (600, int((600 / w) * h)))
        rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), dtype=np.uint8)

        locs = face_recognition.face_locations(rgb, number_of_times_to_upsample=1)
        encs = face_recognition.face_encodings(rgb, known_face_locations=locs, num_jitters=1)
        live_encodings.extend(encs)

        # Liveness: track nose offset relative to eye center
        if locs:
            for landmarks in face_recognition.face_landmarks(rgb, face_locations=locs):
                nose_tip = landmarks.get('nose_tip', [])
                left_eye = landmarks.get('left_eye', [])
                right_eye = landmarks.get('right_eye', [])
                if nose_tip and left_eye and right_eye:
                    nose_x = nose_tip[len(nose_tip) // 2][0]
                    left_cx = sum(p[0] for p in left_eye) / len(left_eye)
                    right_cx = sum(p[0] for p in right_eye) / len(right_eye)
                    eye_center_x = (left_cx + right_cx) / 2
                    eye_width = abs(right_cx - left_cx)
                    if eye_width > 0:
                        nose_offsets.append((nose_x - eye_center_x) / eye_width)

    cap.release()
    print(f"🎞️ Got {len(live_encodings)} encoding(s), {len(nose_offsets)} nose offset(s)", flush=True)
    return live_encodings, nose_offsets

def _check_head_turn(nose_offsets):
    """Return True if nose offsets show a real head turn (range >= 0.3)."""
    if len(nose_offsets) < 3:
        return False
    offset_range = max(nose_offsets) - min(nose_offsets)
    print(f"🔄 Head turn range: {offset_range:.3f} (need >= 0.3)", flush=True)
    return offset_range >= 0.3

def register_verification_routes(app):
    @app.route('/verify', methods=['POST'])
    def verify_user():
        timestamp = datetime.datetime.now().strftime("%H-%M-%S")
        print(f"\n--- NEW VERIFICATION REQUEST AT {timestamp} ---", flush=True)

        video_path = None
        profile_path = None
        frame_path = None

        try:
            user_id = request.form.get('user_id', 'unknown')
            print(f"⏳ Receiving files for user {user_id}...", flush=True)

            if 'video' not in request.files:
                return jsonify({"error": "Missing video file", "match": False, "score": 0.0}), 400
            if 'profile_image' not in request.files:
                return jsonify({"error": "Missing profile_image file", "match": False, "score": 0.0}), 400

            video_file = request.files['video']
            profile_file = request.files['profile_image']

            video_path = os.path.join(EVIDENCE_FOLDER, f"{timestamp}_{user_id}_video.mp4")
            profile_path = os.path.join(EVIDENCE_FOLDER, f"{timestamp}_{user_id}_profile.jpg")
            video_file.save(video_path)
            profile_file.save(profile_path)
            print(f"✅ Files saved to {EVIDENCE_FOLDER}", flush=True)

            # 1. PROFILE ENCODING
            print("1️⃣ Processing profile picture...", flush=True)
            profile_encodings = _get_profile_encodings(profile_path)
            if not profile_encodings:
                print("❌ No face found in profile picture", flush=True)
                return jsonify({"error": "No face found in profile picture", "match": False, "score": 0.0}), 200
            print(f"✅ Got {len(profile_encodings)} profile encoding(s)", flush=True)

            # 2. LIVE FRAME(S)
            print("2️⃣ Processing video...", flush=True)
            frame_file = request.files.get('video_frame')
            if frame_file:
                # Use pre-captured still frame sent from Flutter
                frame_path = os.path.join(EVIDENCE_FOLDER, f"{timestamp}_{user_id}_frame.jpg")
                frame_file.save(frame_path)
                img = face_recognition.load_image_file(frame_path)
                locs = face_recognition.face_locations(img, number_of_times_to_upsample=1)
                live_encodings = face_recognition.face_encodings(img, known_face_locations=locs, num_jitters=1)
                nose_offsets = []  # no liveness from still frame — handled by video below
                print("  (using captured still frame)", flush=True)
            else:
                live_encodings, nose_offsets = _extract_frames_and_liveness(video_path)
                if live_encodings is None:
                    return jsonify({"error": "Video too short", "match": False, "score": 0.0}), 400

            if not live_encodings:
                print("❌ No face detected in video", flush=True)
                return jsonify({"error": "No face found in video selfie", "match": False, "score": 0.0}), 200

            # 3. LIVENESS CHECK
            print("3️⃣ Checking liveness...", flush=True)
            if nose_offsets and not _check_head_turn(nose_offsets):
                print("🚫 REJECTED: Liveness check failed", flush=True)
                return jsonify({"error": "Liveness check failed — please turn your head as instructed", "match": False, "score": 0.0}), 200

            # 4. FACE MATCH — best distance across all combinations
            print("4️⃣ Comparing faces...", flush=True)
            all_distances = [
                face_recognition.face_distance([p_enc], l_enc)[0]
                for p_enc in profile_encodings
                for l_enc in live_encodings
            ]
            best_distance = min(all_distances)
            score = round((1 - best_distance) * 100, 2)
            is_match = bool(best_distance <= TOLERANCE)

            print(f"📊 Score: {score}% | Distance: {best_distance:.4f} | Threshold: {TOLERANCE}", flush=True)
            print(f"📈 All distances: {sorted([round(d, 4) for d in all_distances])}", flush=True)
            print(f"🎯 DECISION: {'✅ MATCH' if is_match else '❌ NO MATCH'}", flush=True)

            return jsonify({"status": "success", "match": is_match, "score": score})

        except Exception as e:
            import traceback
            print(f"🔥 CRASH: {e}", flush=True)
            traceback.print_exc()
            return jsonify({"error": str(e), "match": False, "score": 0.0}), 500

        finally:
            # Clean up temp files
            for path in [video_path, frame_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                        print(f"🧹 Cleaned up {os.path.basename(path)}", flush=True)
                    except Exception:
                        pass
