# moderation_logic.py
import easyocr
import numpy as np
import cv2
import re
import warnings

# Suppress PyTorch CPU warnings
warnings.filterwarnings("ignore", category=UserWarning)

reader = easyocr.Reader(['en'], gpu=False) 

def is_scam_text(text):
    text = text.lower()
    
    # 1. THE HANDLE CATCHER (@, _, ig:)
    if re.search(r'[@©_]|\big[\s:\-]+|\bsnap[\s:\-]+|\bsc[\s:\-]+|\btele[\s:\-]+|\btg[\s:\-]+', text):
        return True

    words = text.split()
    for word in words:
        # 2. THE DOT CATCHER (e.g., srujxn.18)
        if re.search(r'[a-z0-9]\.[a-z0-9]', word):
            return True

        # 3. ALPHANUMERIC MASHUP CATCHER (e.g., salilvi103)
        has_letter = re.search(r'[a-z]', word)
        has_number = re.search(r'[0-9]', word)

        if has_letter and has_number:
            if len(word) <= 5: continue
            if re.search(r'(19|20)\d{2}', word): continue
            if word.endswith('s') and word[:-1].isdigit(): continue
            if re.search(r'\b\d+(st|nd|rd|th)\b', word): continue
            return True

    # 4. SMART PHONE NUMBER CATCHER
    trick_text = text.replace('o', '0').replace('l', '1').replace('s', '5')
    compact_text = re.sub(r'[\s\-\.\(\)\+]', '', trick_text)
    if re.search(r'\d{8,}', compact_text):
        return True

    # 5. BLOCKED WORDS (Scam & Competitors)
    blocked_words = [
        'telegram', 'snapchat', 'instagram', 'whatsapp', 'tinder', 'bumble', 
        'incall', 'outcall', 'ratecard', 'cashmeet', 'paytomeet', 'paid'
    ]
    if any(b in text for b in blocked_words):
        return True

    return False

def check_image_for_text(image_bytes):
    try:
        image_array = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        results_normal = reader.readtext(gray, detail=1)
        extracted_words = [text.strip(".,'\"-~") for (bbox, text, prob) in results_normal if prob > 0.35]
                
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced_gray = clahe.apply(gray)
        results_enhanced = reader.readtext(enhanced_gray, detail=1)
        
        extracted_words += [text.strip(".,'\"-~") for (bbox, text, prob) in results_enhanced if prob > 0.55]
                
        combined_text = " ".join(list(set(filter(None, extracted_words))))
        
        if combined_text.strip():
            return is_scam_text(combined_text)
        return False 
        
    except Exception as e:
        print(f"❌ EasyOCR Error: {e}", flush=True)
        return False