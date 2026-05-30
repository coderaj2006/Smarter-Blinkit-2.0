import base64
import os
import bcrypt
import numpy as np
import cv2
import face_recognition
from datetime import datetime, timedelta
from typing import List, Optional
import jwt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from dotenv import load_dotenv
from database import get_db
from models import User, RoleEnum

load_dotenv()

# --- Password Hashing (bcrypt direct — avoids passlib/bcrypt 4.x incompatibility) ---
def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt. Returns a utf-8 string for DB storage."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison of a plaintext password against a stored bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

# --- Configuration for JWT Token Generation ---
SECRET_KEY = os.getenv("JWT_SECRET", "fallback-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

router = APIRouter(prefix="/api/auth", tags=["auth"])

class FaceLoginRequest(BaseModel):
    email: EmailStr
    image_base64: str

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: RoleEnum
    image_base64: str

class PasswordLoginRequest(BaseModel):
    email: EmailStr
    password: str

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

async def get_stored_face_embedding(email: str, db: AsyncSession) -> Optional[List[float]]:
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalars().first()
    if user and user.face_embedding:
        return user.face_embedding
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
async def face_login(payload: FaceLoginRequest, db: AsyncSession = Depends(get_db)):
    # 1. Fetch stored embedding for the user
    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not user.face_embedding:
        raise HTTPException(
            status_code=404, 
            detail="User not found or no face profile registered."
        )
        
    known_encoding = np.array(user.face_embedding)

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
        user_id = user.id
        user_role = user.role.value 
        
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

@router.post("/register")
async def register_user(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        img = decode_base64_image(payload.image_base64)
        if img is None:
            raise ValueError("Empty image")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image payload.")

    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb_img)

    if len(face_locations) == 0:
        raise HTTPException(status_code=400, detail="No face detected. Please try again.")
    elif len(face_locations) > 1:
        raise HTTPException(status_code=400, detail="Multiple faces detected.")

    face_encoding = face_recognition.face_encodings(rgb_img, face_locations)[0]

    # Create new user — password is bcrypt-hashed before storage
    new_user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        face_embedding=face_encoding.tolist()
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Automatically generate token after registration
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.email, "user_id": new_user.id, "role": new_user.role.value},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "message": "User registered successfully"
    }

@router.post("/login")
async def password_login(payload: PasswordLoginRequest, db: AsyncSession = Depends(get_db)):
    """Standard email + password login. Verifies bcrypt hash."""
    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    # Use constant-time verify to prevent user enumeration via timing attacks.
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "user_id": user.id, "role": user.role.value},
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "message": "Login successful",
    }
