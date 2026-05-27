import base64
import numpy as np
import cv2
import face_recognition
from datetime import datetime, timedelta
from typing import List, Optional
import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

# --- Configuration for JWT Token Generation ---
SECRET_KEY = "your-very-secure-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

router = APIRouter(prefix="/api/auth", tags=["auth"])

class FaceLoginRequest(BaseModel):
    email: EmailStr
    image_base64: str

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Generates a secure JWT containing user credentials."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_stored_face_embedding(email: str) -> Optional[List[float]]:
    """
    MOCK FUNCTION: Retrieves a pre-saved list of 128-dimensional floats.
    In a real application, you would query the database using SQLAlchemy:
    user = db.query(User).filter(User.email == email).first()
    return user.face_embedding if user else None
    """
    if email == "test@example.com":
        return [0.0] * 128  # Placeholder for a real 128D numpy array list
    return None

def decode_base64_image(base64_string: str) -> np.ndarray:
    """
    Decodes a base64 string from a browser canvas/webcam into a numpy array (BGR image)
    capable of being read by OpenCV and face_recognition.
    """
    # 1. Clean HTML prefix if sent by the browser (e.g. "data:image/jpeg;base64,...")
    if "," in base64_string:
        base64_string = base64_string.split(",")[1]
    
    # 2. Decode the string into raw bytes
    img_data = base64.b64decode(base64_string)
    
    # 3. Convert bytes into a Numpy array and decode it into an OpenCV image
    np_arr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    return img

@router.post("/face-login")
async def face_login(payload: FaceLoginRequest):
    # 1. Fetch stored embedding for the user
    stored_embedding = get_stored_face_embedding(payload.email)
    if not stored_embedding:
        raise HTTPException(
            status_code=404, 
            detail="User not found or no face profile registered."
        )
        
    known_encoding = np.array(stored_embedding)

    # 2. Decode the incoming webcam frame
    try:
        img = decode_base64_image(payload.image_base64)
        if img is None:
            raise ValueError("Empty image data")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image payload.")
        
    # OpenCV loads images in BGR format, but face_recognition uses RGB.
    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # 3. Detect face locations in the incoming frame
    face_locations = face_recognition.face_locations(rgb_img)
    
    # EDGE CASE 1: No faces found
    if len(face_locations) == 0:
        raise HTTPException(
            status_code=400, 
            detail="No face detected in the frame. Please adjust your lighting and try again."
        )
    # EDGE CASE 2: Multiple faces found (security risk)
    elif len(face_locations) > 1:
        raise HTTPException(
            status_code=400, 
            detail="Multiple faces detected. Please ensure only you are in the camera frame."
        )
        
    # 4. Extract the embedding for the single detected face
    unknown_encoding = face_recognition.face_encodings(rgb_img, face_locations)[0]

    # 5. Compare the faces using Euclidean distance
    TOLERANCE = 0.6  # Standard strictness threshold
    matches = face_recognition.compare_faces([known_encoding], unknown_encoding, tolerance=TOLERANCE)
    face_distances = face_recognition.face_distance([known_encoding], unknown_encoding)
    
    if matches[0]:
        # Verification successful! 
        # Ideally, we would grab user_id and role from the DB object here.
        user_id = 1
        user_role = "buyer" 
        
        # 6. Generate secure JWT
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": payload.email, "user_id": user_id, "role": user_role},
            expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token, 
            "token_type": "bearer",
            "message": "Biometric login successful",
            "confidence_distance": round(face_distances[0], 4)
        }
    else:
        # Verification failed
        raise HTTPException(status_code=401, detail="Face does not match registered profile.")
