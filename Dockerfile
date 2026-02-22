# Use a base image that ALREADY has dlib and face_recognition installed
FROM animcogn/face_recognition:cpu

# Set up the working directory
WORKDIR /app

# Copy your code to the container
COPY . /app

# Install ONLY the web frameworks (Flask, Supabase)
# We do NOT install dlib or face_recognition here because they are already inside!
RUN pip install flask gunicorn supabase requests imutils opencv-python-headless

# Start the server on port 10000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000", "--timeout", "120"]