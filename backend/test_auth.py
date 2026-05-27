import base64
import urllib.request
import cv2
import numpy as np
import face_recognition
from fastapi.testclient import TestClient

from main import app
import auth

# 1. Download a sample face image
url = "https://raw.githubusercontent.com/ageitgey/face_recognition/master/examples/obama.jpg"
image_path = "obama.jpg"
print("Downloading sample face image...")
urllib.request.urlretrieve(url, image_path)

# 2. Extract the actual encoding to use as our "stored" DB encoding
print("Extracting encoding for the mock database...")
img = face_recognition.load_image_file(image_path)
encodings = face_recognition.face_encodings(img)
if not encodings:
    print("No face found in sample image!")
    exit(1)
    
real_encoding = encodings[0].tolist()

# 3. Patch the auth module's mock function to return this exact encoding
# This simulates the database already knowing what this person looks like.
def mocked_get_stored_face_embedding(email: str):
    if email == "test@example.com":
        return real_encoding
    return None
auth.get_stored_face_embedding = mocked_get_stored_face_embedding

# 4. Prepare the base64 payload
with open(image_path, "rb") as image_file:
    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    
# Add a fake HTML canvas prefix to ensure our cleanup logic works
base64_payload = "data:image/jpeg;base64," + encoded_string

# 5. Run the test using FastAPI TestClient
print("Sending POST request to /api/auth/face-login...")
client = TestClient(app)
response = client.post(
    "/api/auth/face-login",
    json={
        "email": "test@example.com",
        "image_base64": base64_payload
    }
)

print(f"\n--- TEST RESULTS (Status: {response.status_code}) ---")
import json
try:
    print(json.dumps(response.json(), indent=2))
except Exception:
    print(response.text)
