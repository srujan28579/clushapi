# moderation_logic.py
import easyocr
import numpy as np
import cv2
import re
import warnings
from nudenet import NudeDetector

# Suppress PyTorch CPU warnings
warnings.filterwarnings("ignore", category=UserWarning)

reader = easyocr.Reader(['en'], gpu=True)
nude_detector = NudeDetector()

# Classes that should always be rejected
NSFW_BLOCKED_CLASSES = {
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "MALE_BREAST_EXPOSED",
    "ANUS_EXPOSED",
    "BUTTOCKS_EXPOSED",
    "BELLY_EXPOSED",
    "ARMPITS_EXPOSED",
}
NSFW_SCORE_THRESHOLD = 0.45

WORD_TO_DIGIT = {
    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
    # shorthand / slang
    'niner': '9', 'ate': '8', 'oh': '0',
    # phonetic/casual spellings
    'zer0': '0', 'won': '1', 'tu': '2', 'too': '2', 'to': '2',
    'thre': '3', 'fo': '4', 'for': '4', 'fiv': '5',
    'siks': '6', 'sev': '7', 'sevn': '7', 'eigh': '8', 'nin': '9',
    # Hindi/Hinglish number words (common in India)
    'ek': '1', 'do': '2', 'teen': '3', 'char': '4', 'paanch': '5',
    'chhe': '6', 'saat': '7', 'aath': '8', 'nau': '9', 'shunya': '0',
}

MULTIPLIERS = {
    'double': 2, 'twice': 2,
    'triple': 3, 'treble': 3, 'tiple': 3, 'tripe': 3,  # include OCR misreads
    'quadruple': 4, 'quad': 4,
}

def _expand_multipliers(text):
    """Expand 'double three' → 'three three', 'triple eight' → 'eight eight eight'."""
    tokens = re.split(r'(\s+)', text)  # keep whitespace as separate tokens
    result = []
    i = 0
    while i < len(tokens):
        token = tokens[i].lower().strip()
        if token in MULTIPLIERS:
            count = MULTIPLIERS[token]
            # look ahead for the next non-space token
            j = i + 1
            while j < len(tokens) and tokens[j].strip() == '':
                j += 1
            if j < len(tokens):
                next_word = tokens[j].strip()
                result.append(' '.join([next_word] * count))
                i = j + 1
                continue
        result.append(tokens[i])
        i += 1
    return ' '.join(result)

def _words_to_digits(text):
    """Expand multipliers then replace spelled-out number words with digits."""
    text = _expand_multipliers(text)
    tokens = re.split(r'[\s\-,]+', text)
    converted = [WORD_TO_DIGIT.get(t.lower(), t) for t in tokens]
    return ''.join(converted)

def _has_spelled_out_number(text):
    """Return True if consecutive number words add up to 8+ digits."""
    text = _expand_multipliers(text)
    tokens = re.split(r'[\s\-,]+', text)
    run = 0
    for token in tokens:
        if token.lower() in WORD_TO_DIGIT or token.isdigit():
            run += 1
            if run >= 8:
                return True
        else:
            run = 0
    return False

def is_scam_text(text):
    text = text.lower()

    # 1. SYMBOL-BASED HANDLE CATCHER (@, _, ©)
    if re.search(r'[@©]', text):
        return True

    # 2. PLATFORM KEYWORD CATCHER (snap, ig, tg, wa, discord, etc.)
    if re.search(
        r'\b(ig|snap|sc|tele|tg|wa|whats|discord|insta|twitter|fb|facebook|onlyfans|of)\s*[:\-\s]',
        text
    ):
        return True

    # 3. BLOCKED PLATFORM / SCAM WORDS
    blocked_words = [
        'telegram', 'snapchat', 'instagram', 'whatsapp', 'tinder', 'bumble',
        'discord', 'twitter', 'onlyfans', 'incall', 'outcall', 'ratecard',
        'cashmeet', 'paytomeet', 'paid'
    ]
    if any(b in text for b in blocked_words):
        return True

    # 4. SMART PHONE NUMBER CATCHER
    # Covers OCR misreads: B→8, Z→2, D/Q→0, G→6, S→5, l/I→1, o/O→0
    trick_text = (text
        .replace('o', '0').replace('O', '0').replace('D', '0').replace('Q', '0')
        .replace('l', '1').replace('I', '1').replace('|', '1')
        .replace('s', '5').replace('S', '5')
        .replace('B', '8').replace('b', '8')
        .replace('Z', '2').replace('z', '2')
        .replace('G', '6')
        .replace('i', '1')
    )
    compact_text = re.sub(r'[\s\-\.\(\)\+\/\\*x×]', '', trick_text)
    if re.search(r'\d{7,}', compact_text):  # 7+ to catch partial reads
        return True

    # 5. SPELLED-OUT NUMBER CATCHER (e.g., "nine eight seven six five four three two")
    if _has_spelled_out_number(text):
        return True

    # Also convert words→digits in the full text and recheck for digit runs
    digit_converted = re.sub(r'[\s\-\.\(\)\+\/\\]', '', _words_to_digits(text))
    if re.search(r'\d{8,}', digit_converted):
        return True

    words = text.split()
    for word in words:
        # 5. DOT CATCHER (e.g., srujxn.18, user.name)
        if re.search(r'[a-z0-9]\.[a-z]{2,}', word):
            return True

        # 6. UNDERSCORE IN WORD (classic handle pattern: my_name)
        if '_' in word and len(word) > 3:
            return True

        # 7. ALPHANUMERIC MASHUP CATCHER (e.g., salilvi103)
        has_letter = re.search(r'[a-z]', word)
        has_number = re.search(r'[0-9]', word)
        if has_letter and has_number and len(word) > 5:
            if re.search(r'(19|20)\d{2}', word): continue  # year is fine
            if re.search(r'^\d+(st|nd|rd|th)$', word): continue  # ordinals fine
            if word.endswith('s') and word[:-1].isdigit(): continue  # "10s" fine
            return True

    return False

def check_image_for_nudity(image_bytes):
    """Returns True if the image contains nudity/NSFW content."""
    try:
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        detections = nude_detector.detect(tmp_path)
        os.remove(tmp_path)
        for d in detections:
            if d['class'] in NSFW_BLOCKED_CLASSES and d['score'] >= NSFW_SCORE_THRESHOLD:
                print(f"🔞 NSFW detected: {d['class']} ({d['score']:.2f})", flush=True)
                return True
        return False
    except Exception as e:
        print(f"❌ NudeNet Error: {e}", flush=True)
        return False

def _ocr_variants(img):
    """Return preprocessed image variants to maximise OCR coverage."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    inverted = cv2.bitwise_not(enhanced)           # catches white-on-dark text
    adaptive = cv2.adaptiveThreshold(              # catches faint/low-contrast text
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    return [enhanced, inverted, adaptive]

def check_image_for_text(image_bytes):
    try:
        image_array = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        # Resize to cap GPU memory
        h, w = img.shape[:2]
        if w > 1024:
            img = cv2.resize(img, (1024, int((1024 / w) * h)))

        # Check nudity first (fast rejection before OCR)
        if check_image_for_nudity(image_bytes):
            return True

        # Run OCR on all preprocessing variants and collect all text
        seen = set()
        extracted_words = []
        for variant in _ocr_variants(img):
            for (bbox, text, prob) in reader.readtext(variant, detail=1):
                cleaned = text.strip(".,'\"-~ ")
                if prob > 0.25 and cleaned and cleaned.lower() not in seen:
                    seen.add(cleaned.lower())
                    extracted_words.append(cleaned)

        combined_text = " ".join(extracted_words)
        print(f"📝 OCR extracted: {combined_text!r}", flush=True)
        if combined_text.strip():
            return is_scam_text(combined_text)
        return False

    except Exception as e:
        print(f"❌ EasyOCR Error: {e}", flush=True)
        return False