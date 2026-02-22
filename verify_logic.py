# verify_logic.py
import os
import cv2
import face_recognition
import datetime
from flask import request, jsonify

# Setup folders
EVIDENCE_FOLDER = r'C:\Users\Public\Clush_Evidence' 
if not os.path.exists(EVIDENCE_FOLDER):
    os.makedirs(EVIDENCE_FOLDER)

TOLERANCE = 0.50 

def get_face_encoding(image_path):
    try:
        img_bgr = cv2.imread(image_path)
        if img_bgr is None: return None
        # Convert to Grayscale for detection (More robust)
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        
        face_locations = face_recognition.face_locations(img_gray)
        if not face_locations: return None
        
        encodings = face_recognition.face_encodings(img_rgb, face_locations)
        if not encodings: return None
        return encodings[0]
    except Exception as e:
        print(f"❌ Processing Failed: {e}")
        return None

def register_verification_routes(app):
    """
    This function attaches the '/verify' route to the main server.
    """
    @app.route('/verify', methods=['POST'])
    def verify_user():
        timestamp = datetime.datetime.now().strftime("%H-%M-%S")
        print(f"\n--- NEW VERIFICATION REQUEST AT {timestamp} ---")

        try:
            # 1. Check Files
            if 'profile' in request.files: profile_file = request.files['profile']
            elif 'image' in request.files: profile_file = request.files['image']
            else: return jsonify({"status": "error", "message": "Missing 'profile' key"}), 400

            if 'video' not in request.files: return jsonify({"status": "error", "message": "Missing 'video' key"}), 400
            video_file = request.files['video']

            # 2. Save Files
            profile_path = os.path.join(EVIDENCE_FOLDER, f"{timestamp}_profile.jpg")
            video_path = os.path.join(EVIDENCE_FOLDER, f"{timestamp}_video.mp4")
            profile_file.save(profile_path)
            video_file.save(video_path)

            # 3. Analyze
            print("   Processing Profile Picture...")
            known_encoding = get_face_encoding(profile_path)
            if known_encoding is None:
                return jsonify({"status": "fail", "match": False, "message": "No face in profile pic"}), 200
            
            print("   Processing Video...")
            video_capture = cv2.VideoCapture(video_path)
            success, frame = video_capture.read()
            video_capture.release()
            if not success: return jsonify({"status": "error", "message": "Video empty"}), 400

            frame_path = os.path.join(EVIDENCE_FOLDER, f"{timestamp}_frame_used.jpg")
            cv2.imwrite(frame_path, frame)
            
            unknown_encoding = get_face_encoding(frame_path)
            if unknown_encoding is None:
                return jsonify({"status": "fail", "match": False, "message": "No face in video"}), 200
            
            # 4. Compare
            distance = face_recognition.face_distance([known_encoding], unknown_encoding)[0]
            is_match = distance <= TOLERANCE

            print(f"📊 RESULT: Distance {distance:.4f} (Limit: {TOLERANCE})")
            print(f"🎯 DECISION: {'MATCH ✅' if is_match else 'NO MATCH ❌'}")
            
            return jsonify({
                "status": "success", 
                "match": bool(is_match), 
                "score": float(distance)
            }), 200

        except Exception as e:
            print(f"🔥 CRITICAL ERROR: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500