<![CDATA[# SmartMarket — Smarter Blinkit 2.0

> **An AI-driven, location-aware local commerce platform** that connects buyers to the nearest verified sellers using biometric authentication, semantic product search, and a real-time inventory pipeline — all in under 10 km.

---

## Table of Contents

- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Local Setup & Installation](#local-setup--installation)
- [Environment Variables](#environment-variables)
- [Running the Application](#running-the-application)
- [API Overview](#api-overview)

---

## Key Features

### 🔐 Biometric Dual-Login Dashboard
Two distinct authenticated dashboards — one for buyers, one for sellers — protected by a dual-factor login system. Users register and authenticate via **OpenCV + face_recognition** (128-dimension facial embedding stored as a PostgreSQL `ARRAY(Float)` column). A fallback **bcrypt email/password** login is available for environments without camera access. All sessions are issued as signed **HS256 JWTs** with a 60-minute expiry.

### 🔍 Intent-Based Semantic Search
The buyer search endpoint (`GET /api/products/search`) accepts a natural-language query and performs **case-insensitive ILIKE matching** across both product name and description fields simultaneously. Results are pre-filtered by a **±0.5° bounding box** at the database level before any Python-side computation runs, keeping query latency low even against a large catalog.

### 📍 Geolocation-Based Store Sorting
Every search result is ranked by **Haversine great-circle distance** between the buyer's GPS coordinates and each seller's registered shop location. The bounding-box pre-filter eliminates shops beyond ~55 km before the distance calculation runs, ensuring the sort is both accurate and efficient. Distance is surfaced in the response payload as `distance_km` for display in the UI.

### 📦 Barcode-Based Inventory Management
Sellers can increment stock for any product by scanning its barcode via the browser's camera (`html5-qrcode`). The `PATCH /api/inventory/update-by-barcode` endpoint matches the scanned string against the product catalog using a fuzzy ILIKE search on name and description, then atomically increments `stock_quantity` by 1. New seller accounts are auto-seeded with 300 randomised inventory rows on first login so the dashboard is never empty.

### 💳 Exception-Safe Mock Payment Pipeline
A full Razorpay checkout flow — order creation → modal → HMAC-SHA256 signature verification → atomic stock decrement — implemented with a bulletproof exception safety model. The frontend hook (`useRazorpayCheckout`) uses a dedicated `async handler` with its own `try/catch` that resets `isProcessing` state **immediately** in both the success and failure paths, preventing the cart from ever freezing on "Processing...". The backend wraps all DB writes in `try/except` and returns structured JSON errors on failure rather than silent 500s.

---

## Tech Stack

### Backend
| Package | Version | Role |
|---|---|---|
| FastAPI | 0.104.1 | Async REST API framework |
| Uvicorn | 0.24.0 | ASGI server |
| SQLAlchemy | 2.0.23 | Async ORM with PostgreSQL |
| asyncpg | 0.29.0 | Async PostgreSQL driver |
| Pydantic | 2.5.2 | Request/response validation |
| PyJWT | 2.8.0 | JWT generation and verification |
| bcrypt | 5.0.0 | Password hashing |
| face_recognition | 1.3.0 | 128-d facial embedding extraction |
| opencv-python-headless | 4.8.1.78 | Image decoding and colour conversion |
| python-dotenv | 1.0.0 | Environment variable loading |

### Frontend
| Package | Version | Role |
|---|---|---|
| React | 19.2.6 | UI component framework |
| TypeScript | 6.0.2 | Static typing |
| Vite | 8.0.12 | Build tool and dev server |
| Tailwind CSS | 3.4.19 | Utility-first styling |
| html5-qrcode | 2.3.8 | Browser barcode/QR scanning |
| lucide-react | 1.16.0 | Icon library |
| clsx + tailwind-merge | latest | Conditional class utilities |

### Core Utilities
| Tool | Purpose |
|---|---|
| OpenCV (headless) | Decodes base64 webcam frames, BGR→RGB conversion |
| face_recognition (dlib) | Generates and compares 128-d facial embeddings |
| Razorpay JS SDK | Payment modal, order lifecycle, HMAC verification |
| html5-qrcode | Camera-based barcode scanning in the browser |
| PostgreSQL `ARRAY(Float)` | Native vector storage for face embeddings |
| Haversine formula | Great-circle distance calculation for store ranking |

---

## Project Structure

```
Smarter-Blinkit-2.0/
│
├── .env                          # Root secrets (DATABASE_URL, JWT_SECRET, Razorpay keys)
├── .gitignore                    # Comprehensive ignore rules for both stacks
├── README.md
│
├── backend/
│   ├── main.py                   # FastAPI app, all route handlers
│   ├── auth.py                   # /api/auth/* — register, face-login, password-login
│   ├── models.py                 # SQLAlchemy ORM models (User, Shop, ProductCatalog, SellerInventory)
│   ├── database.py               # Async engine, session factory, Base
│   ├── utils.py                  # Haversine distance calculation
│   ├── seed_db.py                # Initial database seeding script
│   ├── seed_big_basket.py        # BigBasket CSV → ProductCatalog bulk import
│   ├── test_auth.py              # Auth endpoint tests
│   ├── requirements.txt          # Pinned Python dependencies
│   └── venv/                     # Python virtual environment (git-ignored)
│
└── frontend/
    ├── index.html
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── tsconfig.json
    ├── package.json
    ├── .env                      # VITE_RAZORPAY_KEY_ID (git-ignored)
    │
    └── src/
        ├── main.tsx              # React entry point
        ├── App.tsx               # Root component, routing logic
        │
        ├── components/
        │   ├── Login.tsx         # Biometric + password login UI
        │   ├── DashboardWrapper.tsx  # Role-based dashboard switcher
        │   ├── BuyerDashboard.tsx    # Search, cart, checkout UI
        │   ├── SellerDashboard.tsx   # Inventory management UI
        │   ├── ProductCard.tsx       # Individual product display
        │   └── BarcodeScanner.tsx    # html5-qrcode camera component
        │
        ├── hooks/
        │   └── useRazorpayCheckout.ts  # Exception-safe payment hook
        │
        ├── context/
        │   └── AppContext.tsx    # Global auth state, cart state
        │
        └── types/
            └── razorpay.d.ts    # Razorpay SDK type declarations
```

---

## Local Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ (running locally or via Docker)
- A C++ build toolchain for `dlib` (required by `face_recognition`)
  - **Windows**: [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with "Desktop development with C++"
  - **macOS**: `xcode-select --install`
  - **Linux**: `sudo apt install build-essential cmake`

---

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/Smarter-Blinkit-2.0.git
cd Smarter-Blinkit-2.0
```

### 2. Backend — Python Virtual Environment

```bash
cd backend

# Create and activate the virtual environment
python -m venv venv

# Windows (CMD)
venv\Scripts\activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# macOS / Linux
source venv/bin/activate

# Install all pinned dependencies
pip install -r requirements.txt
```

> **Note on `face_recognition`**: This package installs `dlib` from source, which takes 5–10 minutes on first install. Ensure your C++ build toolchain is in place before running `pip install`.

### 3. Frontend — Node Modules

```bash
cd ../frontend
npm install
```

### 4. Database Setup

Create a PostgreSQL database for the project:

```sql
CREATE DATABASE smartmarket;
```

Then seed the product catalog (run from the `backend/` directory with `venv` active):

```bash
# Seed the BigBasket product catalog (~500 products)
python seed_big_basket.py

# Optional: seed test users
python seed_db.py
```

The database tables are created automatically on first server startup via SQLAlchemy's `Base.metadata.create_all`.

---

## Environment Variables

### Root `.env` (backend reads this)

Create a `.env` file in the project root:

```env
# PostgreSQL connection string
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/smartmarket

# JWT signing secret — use a long random string in production
JWT_SECRET=your-super-secret-jwt-key-change-this

# Razorpay credentials — get from dashboard.razorpay.com
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=your_razorpay_key_secret
```

### `frontend/.env` (Vite reads this)

Create a `.env` file inside the `frontend/` directory:

```env
# Must be prefixed with VITE_ to be exposed to the browser bundle
VITE_RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
```

> Both `.env` files are listed in `.gitignore` and will never be committed to the repository.

---

## Running the Application

### Start the FastAPI Backend

Run from the `backend/` directory with the virtual environment active:

```bash
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at `http://127.0.0.1:8000`.  
Interactive API docs (Swagger UI): `http://127.0.0.1:8000/docs`

### Start the React Frontend

Run from the `frontend/` directory in a separate terminal:

```bash
cd frontend
npm run dev
```

The app will be available at `http://localhost:5173`.

---

## API Overview

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | None | Register with face embedding + password |
| `POST` | `/api/auth/login` | None | Email + password login |
| `POST` | `/api/auth/face-login` | None | Biometric login via webcam frame |
| `GET` | `/api/products/search` | Bearer | Location-aware semantic product search |
| `GET` | `/api/seller/inventory` | Bearer (seller) | Fetch seller's full inventory |
| `PATCH` | `/api/seller/inventory/{id}` | Bearer (seller) | Update price or stock quantity |
| `PATCH` | `/api/inventory/update-by-barcode` | Bearer (seller) | Increment stock via barcode scan |
| `POST` | `/api/payments/create-order` | Bearer | Create Razorpay order from cart |
| `POST` | `/api/payments/verify` | Bearer | Verify HMAC signature + decrement stock |

---

## Stage 2 Roadmap

- [ ] Real-time order tracking with WebSockets
- [ ] Seller analytics dashboard (revenue, top products, stock velocity)
- [ ] AI-powered demand forecasting for inventory restocking alerts
- [ ] Multi-image product listings with CDN storage
- [ ] Push notifications for low-stock and order status updates
]]>
