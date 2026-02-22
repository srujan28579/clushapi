import os
import cv2
import face_recognition
import datetime
import numpy as np
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
EVIDENCE_FOLDER = r'C:\Users\Public\Clush_Evidence' 
if not os.path.exists(EVIDENCE_FOLDER):
    os.makedirs(EVIDENCE_FOLDER)

TOLERANCE = 0.50 

def get_face_encoding(image_path):
    """
    ROBUST METHOD:
    1. Loads image.
    2. Converts to Grayscale for detection (Prevents dlib RGB crashes).
    3. Uses Grayscale to find where the face is.
    4. Uses Color image to read the identity.
    """
    try:
        # 1. Load Image using OpenCV
        img_bgr = cv2.imread(image_path)
        if img_bgr is None:
            print(f"❌ Error: Could not read {image_path}")
            return None

        # 2. Create Two Versions
        # Version A: Grayscale (For finding the face location) - Dlib loves this
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        
        # Version B: RGB (For extracting the ID) - Needed for accuracy
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        # 3. Find Face Location using GRAYSCALE (The Bypass)
        # This avoids the "Unsupported image type" crash in the detector
        face_locations = face_recognition.face_locations(img_gray)

        if not face_locations:
            print(f"⚠️ No face found in {os.path.basename(image_path)}")
            return None

        # 4. Extract Identity using RGB + The Location we just found
        # We explicitly tell it WHERE the face is, so it doesn't have to scan the RGB image
        encodings = face_recognition.face_encodings(img_rgb, face_locations)

        if not encodings:
            return None
            
        return encodings[0]

    except Exception as e:
        print(f"❌ Processing Failed: {e}")
        return None

@app.route('/verify', methods=['POST'])
def verify_user():
    timestamp = datetime.datetime.now().strftime("%H-%M-%S")
    print(f"\n--- NEW REQUEST RECEIVED AT {timestamp} ---")

    try:
        # 1. GET FILES
        if 'profile' in request.files:
            profile_file = request.files['profile']
        elif 'image' in request.files:
            profile_file = request.files['image']
        else:
            return jsonify({"status": "error", "message": "Missing 'profile' key"}), 400

        if 'video' not in request.files:
             return jsonify({"status": "error", "message": "Missing 'video' key"}), 400
        
        video_file = request.files['video']

        # 2. SAVE FILES
        profile_path = os.path.join(EVIDENCE_FOLDER, f"{timestamp}_profile.jpg")
        video_path = os.path.join(EVIDENCE_FOLDER, f"{timestamp}_video.mp4")
        
        profile_file.save(profile_path)
        video_file.save(video_path)
        print(f"✅ Files saved to: {EVIDENCE_FOLDER}")

        # 3. PROCESS PROFILE
        print("   Processing Profile Picture...")
        known_encoding = get_face_encoding(profile_path)

        if known_encoding is None:
            print("❌ FAIL: No face found in Profile Picture")
            return jsonify({"status": "fail", "match": False, "message": "No face in profile pic"}), 200
        
        # 4. PROCESS VIDEO
        print("   Processing Video...")
        video_capture = cv2.VideoCapture(video_path)
        success, frame = video_capture.read()
        video_capture.release()

        if not success:
            return jsonify({"status": "error", "message": "Video file was empty"}), 400

        # Save the frame
        frame_path = os.path.join(EVIDENCE_FOLDER, f"{timestamp}_frame_used.jpg")
        cv2.imwrite(frame_path, frame)

        # Process the video frame using the same Robust Method
        unknown_encoding = get_face_encoding(frame_path)

        if unknown_encoding is None:
            print("❌ FAIL: No face found in Video Frame")
            return jsonify({"status": "fail", "match": False, "message": "No face in video"}), 200
        
        # 5. COMPARE
        distance = face_recognition.face_distance([known_encoding], unknown_encoding)[0]
        is_match = distance <= TOLERANCE

        print(f"📊 RESULT: Distance {distance:.4f} (Limit: {TOLERANCE})")
        print(f"🎯 DECISION: {'MATCH ✅' if is_match else 'NO MATCH ❌'}")
        
        return jsonify({
            "status": "success",
            "match": bool(is_match),
            "score": float(distance),
            "message": "Verification Complete"
        }), 200

    except Exception as e:
        print(f"🔥 CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)