import requests

url = 'http://127.0.0.1:5000/verify'

# REPLACE these with your actual file names
profile_pic = 'photo1.jpg'  # Your static profile photo
video_file = 'test.mp4'     # The video you just recorded

print("Sending files... this may take 5-10 seconds...")

try:
    files = {
        'profile': open(profile_pic, 'rb'),
        'video':   open(video_file, 'rb')
    }

    response = requests.post(url, files=files)
    print("\n--- SERVER RESPONSE ---")
    print(response.json())

except Exception as e:
    print(f"Error: {e}")