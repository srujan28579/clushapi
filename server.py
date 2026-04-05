# server.py
import os
import cv2
import face_recognition
import datetime
import httpx
import numpy as np
import traceback
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import socketio
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

app = FastAPI(title="Clush API", version="1.0.0")
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

print("🚀 Clush Server Starting...", flush=True)
database.init_db()
chat_logic.register_chat_events(sio, supabase)

# --- ROUTES ---

@app.post("/moderate_image", summary="Moderate image for nudity and prohibited text")
async def moderate_image(image: UploadFile = File(...)):
    print("\n🔍 --- NEW IMAGE MODERATION REQUEST ---", flush=True)
    image_bytes = await image.read()

    is_nude = await asyncio.to_thread(moderation_logic.check_image_for_nudity, image_bytes)
    if is_nude:
        print("🚨 REJECTED: Nudity/NSFW content.", flush=True)
        return {"status": "rejected", "message": "Nudity and explicit content are strictly prohibited."}

    has_scam_text = await asyncio.to_thread(moderation_logic.check_image_for_text, image_bytes)
    if has_scam_text:
        print("🚨 REJECTED: Prohibited text/contact info.", flush=True)
        return {"status": "rejected", "message": "Images containing handles or contact info are strictly prohibited."}

    print("✅ APPROVED: Image is clean.", flush=True)
    return {"status": "approved"}


@app.post("/verify", summary="Verify user face against profile picture")
async def verify_face(
    user_id: str = Form(...),
    video: UploadFile = File(...)
):
    print("\n📥 --- NEW VIDEO VERIFICATION REQUEST ---", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = os.path.join(UPLOAD_FOLDER, f"video_{user_id}_{timestamp}.mp4")

    try:
        # 1. Fetch profile photos from Supabase
        user_data = await asyncio.to_thread(
            lambda: supabase.table('profiles').select('photo_urls').eq('id', user_id).execute()
        )
        if not user_data.data or not user_data.data[0].get('photo_urls'):
            return JSONResponse({"match": False, "score": 0.0, "error": "No profile photos"}, status_code=404)

        photo_urls = user_data.data[0]['photo_urls'][:2]

        # 2. Download profile photos and encode faces (async HTTP + threaded ML)
        print(f"👤 Loading {len(photo_urls)} profile photo(s)...", flush=True)
        profile_encodings = []

        async with httpx.AsyncClient(timeout=10) as client:
            for url in photo_urls:
                try:
                    resp = await client.get(url)
                    img_array = np.frombuffer(resp.content, np.uint8)
                    raw = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if raw is None:
                        continue
                    p_h, p_w = raw.shape[:2]
                    if p_w > 800:
                        raw = cv2.resize(raw, (800, int((800 / p_w) * p_h)))
                    rgb = np.ascontiguousarray(cv2.cvtColor(raw, cv2.COLOR_BGR2RGB), dtype=np.uint8)

                    def encode_profile(img):
                        locs = face_recognition.face_locations(img, number_of_times_to_upsample=2)
                        return face_recognition.face_encodings(img, known_face_locations=locs, num_jitters=2)

                    encs = await asyncio.to_thread(encode_profile, rgb)
                    profile_encodings.extend(encs)
                except Exception as e:
                    print(f"⚠️ Skipping photo: {e}", flush=True)

        if not profile_encodings:
            print("❌ No face encodings from profile photos", flush=True)
            return {"match": False, "score": 0.0, "error": "No face detected in any profile picture"}

        print(f"✅ Got {len(profile_encodings)} profile encoding(s)", flush=True)

        # 3. Save video and extract frames (threaded)
        video_bytes = await video.read()
        with open(video_path, 'wb') as f:
            f.write(video_bytes)

        live_encodings, nose_offsets = await asyncio.to_thread(_extract_frames, video_path, user_id)

        if live_encodings is None:
            return {"match": False, "score": 0.0, "error": "Video too short or unreadable"}
        if not live_encodings:
            return {"match": False, "score": 0.0, "error": "No face detected in live video"}

        # 4. Liveness check
        if nose_offsets and len(nose_offsets) >= 3:
            offset_range = max(nose_offsets) - min(nose_offsets)
            head_turned = offset_range >= 0.3
            print(f"🔄 Head turn check: range={offset_range:.3f}, passed={head_turned}", flush=True)
            if not head_turned:
                print("🚫 REJECTED: Liveness check failed", flush=True)
                return {"match": False, "score": 0.0, "error": "Liveness check failed — please turn your head as instructed"}

        # 5. Best match across all combinations
        print(f"🔬 Comparing {len(live_encodings)} live frame(s) vs {len(profile_encodings)} profile encoding(s)...", flush=True)

        def compare():
            distances = [
                face_recognition.face_distance([p], l)[0]
                for p in profile_encodings
                for l in live_encodings
            ]
            return distances

        all_distances = await asyncio.to_thread(compare)
        best_distance = min(all_distances)
        score = round((1 - best_distance) * 100, 2)
        is_match = bool(best_distance <= 0.45)

        print(f"✅ VERIFICATION COMPLETE: Match={is_match}, Score={score}%, Distance={best_distance:.4f}, Threshold=0.45", flush=True)
        print(f"📊 Raw distances: {sorted([round(d, 4) for d in all_distances])}", flush=True)
        return {"match": is_match, "score": score}

    except Exception as e:
        print("\n❌ --- CRASH REPORT ---", flush=True)
        traceback.print_exc()
        return JSONResponse({"match": False, "score": 0.0, "error": str(e)}, status_code=500)

    finally:
        if os.path.exists(video_path):
            try:
                os.remove(video_path)
                print("🧹 Cleaned up temporary video file.", flush=True)
            except Exception as e:
                print(f"⚠️ Could not delete temp file: {e}", flush=True)


def _extract_frames(video_path: str, user_id: str):
    """Blocking frame extraction — called via asyncio.to_thread."""
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print("❌ OpenCV could not open the video file", flush=True)
        cap.release()
        return None, None

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    codec = int(cap.get(cv2.CAP_PROP_FOURCC))
    codec_str = "".join([chr((codec >> 8 * i) & 0xFF) for i in range(4)])
    print(f"🎥 Video: codec={codec_str}, {total_frames} frames @ {fps:.1f}fps", flush=True)

    success, test_frame = cap.read()
    if not success or test_frame is None:
        cap.release()
        print("❌ Could not decode frames — unsupported codec", flush=True)
        return None, None

    debug_path = os.path.join(UPLOAD_FOLDER, f"debug_frame_{user_id}.jpg")
    cv2.imwrite(debug_path, test_frame)
    print(f"🖼️ First frame: {test_frame.shape}, brightness={test_frame.mean():.1f}", flush=True)

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    skip = int(fps)
    usable = total_frames - skip
    if usable < 1:
        skip = 0
        usable = total_frames

    sample_count = min(10, usable)
    sample_positions = [skip + int(i * usable / sample_count) for i in range(sample_count)]
    print(f"📍 Sampling frames at: {sample_positions}", flush=True)

    live_encodings = []
    nose_offsets = []

    for pos in sample_positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ok, frame = cap.read()
        if not ok:
            print(f"  ⚠️ Frame {pos}: read failed", flush=True)
            continue

        h, w = frame.shape[:2]
        if w > 800:
            frame = cv2.resize(frame, (800, int((800 / w) * h)))

        rotations = [
            frame,
            cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE),
            cv2.rotate(frame, cv2.ROTATE_180),
            cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE),
        ]
        locs, rgb_frame = [], None
        for rot in rotations:
            candidate = np.ascontiguousarray(cv2.cvtColor(rot, cv2.COLOR_BGR2RGB), dtype=np.uint8)
            locs = face_recognition.face_locations(candidate, number_of_times_to_upsample=2)
            if locs:
                rgb_frame = candidate
                break

        if not locs or rgb_frame is None:
            print(f"  ⚠️ Frame {pos}: no face in any rotation", flush=True)
            continue

        print(f"  ✅ Frame {pos}: {len(locs)} face(s)", flush=True)
        encs = face_recognition.face_encodings(rgb_frame, known_face_locations=locs, num_jitters=1)
        live_encodings.extend(encs)

        for landmarks in face_recognition.face_landmarks(rgb_frame, face_locations=locs):
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


# Mount SocketIO on the FastAPI app
combined_app = socketio.ASGIApp(sio, app)

if __name__ == '__main__':
    import uvicorn
    print("✅ Clush Server Ready (Port 10000)", flush=True)
    uvicorn.run("server:combined_app", host="0.0.0.0", port=10000, reload=False)
