import face_recognition
import cv2
import imutils
import numpy as np

def check_liveness_video(video_path):
    """
    Scans the video to ensure the user turns their head Left AND Right.
    Returns the best 'Front Facing' frame to use for ID verification.
    """
    cap = cv2.VideoCapture(video_path)
    
    looked_left = False
    looked_right = False
    best_frame = None
    max_face_size = 0
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break 
        
        frame_count += 1
        # Process every 2nd frame (skip 1) for speed
        if frame_count % 2 != 0:
            continue

        # Resize to speed up processing
        frame = imutils.resize(frame, width=600)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # 1. Find Face
        face_locations = face_recognition.face_locations(rgb_frame)
        if not face_locations:
            continue

        # 2. Get Landmarks (Eyes, Nose)
        landmarks_list = face_recognition.face_landmarks(rgb_frame, face_locations)
        if not landmarks_list:
            continue
            
        landmarks = landmarks_list[0]
        
        # 3. Calculate Head Direction
        # Compare Nose Bridge (top) to Left and Right Eyes
        nose_x = landmarks['nose_bridge'][0][0]
        left_eye_x = landmarks['left_eye'][0][0]   # Outer corner
        right_eye_x = landmarks['right_eye'][3][0] # Outer corner
        
        left_dist = nose_x - left_eye_x
        right_dist = right_eye_x - nose_x
        
        # Avoid division by zero
        if right_dist == 0: right_dist = 0.001
        
        ratio = left_dist / right_dist

        if ratio < 0.5: 
            looked_left = True
        elif ratio > 2.0: 
            looked_right = True
        else:
            # Looking Center? Save this frame if it's the clearest/biggest so far
            face_width = face_locations[0][2] - face_locations[0][0]
            if face_width > max_face_size:
                max_face_size = face_width
                best_frame = rgb_frame

    cap.release()

    # 4. Final Report
    if not looked_left:
        return {"passed": False, "message": "Liveness Failed: You did not turn your head LEFT."}
    
    if not looked_right:
        return {"passed": False, "message": "Liveness Failed: You did not turn your head RIGHT."}
        
    if best_frame is None:
        return {"passed": False, "message": "Liveness Failed: Could not find a clear front-facing face."}

    return {"passed": True, "best_frame": best_frame}


def verify_user(profile_path, video_path):
    try:
        # --- STEP 1: LIVENESS CHECK (Video) ---
        print("Processing Video for Liveness...")
        liveness_result = check_liveness_video(video_path)
        
        if not liveness_result['passed']:
            return {"verified": False, "message": liveness_result['message']}

        # --- STEP 2: ID VERIFICATION ---
        print("Liveness Passed. Verifying ID...")
        
        # Load Profile Image
        try:
            profile_img = face_recognition.load_image_file(profile_path)
            profile_enc = face_recognition.face_encodings(profile_img)[0]
        except IndexError:
            return {"verified": False, "message": "No face found in profile photo."}
        except Exception:
            return {"verified": False, "message": "Could not open profile photo."}
        
        # Use the "Best Frame" from the video as the selfie
        video_frame_img = liveness_result['best_frame']

        try:
            video_enc = face_recognition.face_encodings(video_frame_img)[0]
        except IndexError:
            return {"verified": False, "message": "Liveness passed, but could not read face in the video frame."}

        # --- STEP 3: MATCHING MATH (60% Rule) ---
        # distance 0.0 = Perfect Match (100%)
        # distance 0.6 = Standard Match (40%)
        distance = face_recognition.face_distance([profile_enc], video_enc)[0]

        # Convert to Percentage (Higher is better)
        confidence_score = round((1 - distance) * 100, 2)

        print(f"Match Confidence: {confidence_score}%")

        # THE RULE: Must be higher than 60%
        if confidence_score < 60:
            return {
                "verified": False, 
                "message": f"Security Check Failed. Confidence too low ({confidence_score}%). Faces do not match closely enough.",
                "confidence": confidence_score
            }

        return {
            "verified": True, 
            "message": "Verification Successful!",
            "confidence": confidence_score
        }

    except Exception as e:
        return {"verified": False, "error": str(e)}