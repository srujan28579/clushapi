FROM python:3.11-slim

# System dependencies for dlib, face_recognition, opencv, easyocr
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir \
        flask \
        flask-socketio \
        flasgger \
        gunicorn \
        eventlet \
        supabase \
        requests \
        numpy \
        opencv-python-headless \
        imutils \
        easyocr \
        nudenet \
        python-socketio[client] && \
    pip install --no-cache-dir dlib && \
    pip install --no-cache-dir face_recognition

# Copy app code
COPY . .

# EasyOCR and NudeNet download models at runtime by default — pre-download them
# so the first request isn't slow
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)" || true
RUN python -c "from nudenet import NudeDetector; NudeDetector()" || true

EXPOSE 10000

CMD ["uvicorn", "server:combined_app", "--host", "0.0.0.0", "--port", "10000", "--timeout-keep-alive", "180"]
