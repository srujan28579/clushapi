# moderation_logic.py
import cv2
import pytesseract
import numpy as np
import re

# 🔴 TELL PYTHON WHERE TESSERACT IS INSTALLED
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def is_text_overlay(text):
    """
    THE ZERO TOLERANCE POLICY.
    We don't care WHAT they wrote. If there is text in the image, we block it.
    """
    if not text or text.strip() == "": 
        return False
        
    # Extract only letters and numbers (ignores OCR hallucination symbols like ~ * < >)
    words = re.findall(r'[a-zA-Z0-9]+', text)
    
    # Filter out tiny 1-2 letter artifacts that Tesseract sometimes invents from background shadows
    meaningful_words = [w for w in words if len(w) >= 3]
    total_chars = sum(len(w) for w in words)
    
    # If the image contains ANY word 3 letters or longer, OR a total of more than 6 characters combined
    if len(meaningful_words) > 0 or total_chars > 6:
        print(f"🚨 Triggered: ZERO TEXT TOLERANCE. Found {total_chars} alphanumeric characters.", flush=True)
        return True
        
    return False

def check_image_for_text(image_bytes):
    """MULTI-PASS OCR: Scans 3 different ways to catch dark, bright, and shadowed text."""
    try:
        image_array = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        # PASS 1: Standard
        text_standard = pytesseract.image_to_string(gray)
        
        # PASS 2: Inverted (Bright text on dark background)
        inverted = cv2.bitwise_not(gray)
        text_inverted = pytesseract.image_to_string(inverted)
        
        # PASS 3: High Contrast Threshold (Shadows)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text_thresh = pytesseract.image_to_string(thresh)
        
        combined_text = f"{text_standard} {text_inverted} {text_thresh}"
        clean_print = re.sub(r'\n+', ' ', combined_text).strip()
        print(f"🔍 OCR Multi-Pass Read: {clean_print}", flush=True)
        
        # Send it to the Zero Tolerance Executioner
        return is_text_overlay(combined_text)
        
    except Exception as e:
        print(f"❌ OCR Error: {e}", flush=True)
        return False