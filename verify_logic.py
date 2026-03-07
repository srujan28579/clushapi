import os
import cv2
import face_recognition
import datetime
from flask import request, jsonify

# --- CONFIGURATION ---
EVIDENCE_FOLDER = r'C:\Users\Public\Clush_Evidence'
if not os.path.exists(EVIDENCE_FOLDER):
    os.makedirs(EVIDENCE_FOLDER)

TOLERANCE = 0.50 

def register_verification_routes(app):
    @app.route('/verify', methods=['POST'])
    def verify_user():
        timestamp = datetime.datetime.now().strftime("%H-%M-%S")
        print(f"\n--- 🔍 NEW VERIFICATION REQUEST AT {timestamp} ---")

        try:
            # 1. READ FILES FROM FLUTTER APP
            print("⏳ Receiving files from Flutter app...")
            user_id = request.form.get('user_id', 'unknown')
            
            if 'video' not in request.files:
                return jsonify({"error": "Missing video file", "match": False, "score": 0.0}), 400
            
            if 'profile_image' not in request.files:
                return jsonify({"error": "Missing profile_image file", "match": False, "score": 0.0}), 400

            video_file = request.files['video']
            profile_file = request.files['profile_image']
            print("✅ Files received successfully!")

            # 2. SAVE FILES LOCALLY
            video_path = os.path.join(EVIDENCE_FOLDER, f"{timestamp}_{user_id}_video.mp4")
            profile_path = os.path.join(EVIDENCE_FOLDER, f"{timestamp}_{user_id}_profile.jpg")
            
            video_file.save(video_path)
            profile_file.save(profile_path)
            print(f"✅ Evidence saved to {EVIDENCE_FOLDER}")

            # 3. ENCODE PROFILE PIC
            print("1️⃣ Processing Profile Picture...")
            profile_image = face_recognition.load_image_file(profile_path)
            profile_encodings = face_recognition.face_encodings(profile_image)
            
            if not profile_encodings:
                return jsonify({"error": "No face found in profile picture", "match": False, "score": 0.0}), 200
            known_encoding = profile_encodings[0]

            # 4. PROCESS VIDEO
            print("2️⃣ Processing Video Selfie...")
            cap = cv2.VideoCapture(video_path)
            success, frame = cap.read()
            cap.release()
            
            if not success: 
                return jsonify({"error": "Video recording was empty", "match": False, "score": 0.0}), 400

            # Convert BGR to RGB for Face Recognition
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            video_encodings = face_recognition.face_encodings(rgb_frame)
            
            if not video_encodings:
                return jsonify({"error": "No face found in video selfie", "match": False, "score": 0.0}), 200
            unknown_encoding = video_encodings[0]

            # 5. COMPARE FACES
            print("3️⃣ Comparing Faces...")
            distance = face_recognition.face_distance([known_encoding], unknown_encoding)[0]
            is_match = bool(distance <= TOLERANCE)

            print(f"📊 RESULT: Score {distance:.4f}")
            print(f"🎯 DECISION: {'✅ MATCH' if is_match else '❌ NO MATCH'}")

            return jsonify({
                "status": "success", 
                "match": is_match, 
                "score": float(distance)
            })

        except Exception as e:
            error_msg = str(e)
            print(f"🔥 SYSTEM CRASH: {error_msg}")
            # Returning the exact format the Flutter app is printing
            return jsonify({"error": error_msg, "match": False, "score": 0.0}), 500