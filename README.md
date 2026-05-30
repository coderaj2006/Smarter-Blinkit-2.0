# SmartMarket — Smarter Blinkit 2.0

> **An AI-driven, location-aware local commerce platform** that connects buyers to the nearest verified sellers using biometric authentication, semantic product search, and a real-time inventory pipeline — all within 10 km.

<br/>

<div align="center">

![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-6.0-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-3.4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)

</div>

---

## Table of Contents

- [Key Features](#-key-features)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Local Setup](#-local-setup--installation)
- [Environment Variables](#-environment-variables)
- [Running the App](#-running-the-application)
- [API Reference](#-api-reference)
- [Roadmap](#-stage-2-roadmap)

---

## ✨ Key Features

<br/>

### 🔐 Biometric Dual-Login Dashboard
Two distinct authenticated dashboards — buyer and seller — protected by a dual-factor login system.

- Users register and authenticate via **OpenCV + face_recognition** using a 128-dimension facial embedding stored natively as a PostgreSQL `ARRAY(Float)` column
- Fallback **bcrypt email/password** login for environments without camera access
- All sessions issued as signed **HS256 JWTs** with a 60-minute expiry

<br/>

### 🔍 Intent-Based Semantic Search
The buyer search endpoint accepts a natural-language query and runs against the full product catalog.

- **Case-insensitive ILIKE matching** across both product name and description simultaneously
- Results pre-filtered by a **±0.5° bounding box** at the database level before any Python computation runs
- Keeps query latency low even against a large catalog

<br/>

### 📍 Geolocation-Based Store Sorting
Every search result is ranked by proximity to the buyer.

- **Haversine great-circle distance** calculated between the buyer's GPS coordinates and each seller's registered shop location
- Bounding-box pre-filter eliminates shops beyond ~55 km before the sort runs
- Distance surfaced in the response as `distance_km` for display in the UI

<br/>

### 📦 Barcode-Based Inventory Management
Sellers restock products by pointing their camera at a barcode — no manual entry.

- Browser-native scanning via **html5-qrcode**
- `PATCH /api/inventory/update-by-barcode` matches the scanned string against the catalog using fuzzy ILIKE, then atomically increments `stock_quantity`
- New seller accounts are **auto-seeded with 300 randomised inventory rows** on first login so the dashboard is never empty

<br/>

### 💳 Exception-Safe Mock Payment Pipeline
A full Razorpay checkout flow with a bulletproof exception safety model.

- Flow: order creation → Razorpay modal → HMAC-SHA256 signature verification → atomic stock decrement
- Frontend hook (`useRazorpayCheckout`) uses a dedicated `async handler` with its own `try/catch` that resets `isProcessing` **immediately** in both success and failure paths — the cart can never freeze on "Processing..."
- Backend wraps all DB writes in `try/except` and returns structured JSON errors instead of silent 500s

---

## 🛠 Tech Stack

### Backend

| Package | Version | Role |
|---|---|---|
| FastAPI | 0.104.1 | Async REST API framework |
| Uvicorn | 0.24.0 | ASGI server |
| SQLAlchemy | 2.0.23 | Async ORM with PostgreSQL |
| asyncpg | 0.29.0 | Async PostgreSQL driver |
| Pydantic | 2.5.2 | Request / response validation |
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
| html5-qrcode | 2.3.8 | Browser barcode / QR scanning |
| lucide-react | 1.16.0 | Icon library |
| clsx + tailwind-merge | latest | Conditional class utilities |

### Core Utilities

| Tool | Purpose |
|---|---|
| OpenCV (headless) | Decodes base64 webcam frames, BGR → RGB conversion |
| face_recognition (dlib) | Generates and compares 128-d facial embeddings |
| Razorpay JS SDK | Payment modal, order lifecycle, HMAC verification |
| html5-qrcode | Camera-based barcode scanning in the browser |
| PostgreSQL `ARRAY(Float)` | Native vector storage for face embeddings |
| Haversine formula | Great-circle distance calculation for store ranking |

---

## 📁 Project Structure

```
Smarter-Blinkit-2.0/
│
├── .env                          # Root secrets (DATABASE_URL, JWT_SECRET, Razorpay keys)
├── .gitignore
├── README.md
│
├── backend/
│   ├── main.py                   # FastAPI app — all route handlers
│   ├── auth.py                   # /api/auth/* — register, face-login, password-login
│   ├── models.py                 # ORM models: User, Shop, ProductCatalog, SellerInventory
│   ├── database.py               # Async engine, session factory, Base
│   ├── utils.py                  # Haversine distance calculation
│   ├── seed_db.py                # Initial database seeding script
│   ├── seed_big_basket.py        # BigBasket CSV → ProductCatalog bulk import
│   ├── test_auth.py              # Auth endpoint tests
│   └── requirements.txt          # Pinned Python dependencies
│
└── frontend/
    ├── index.html
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── package.json
    ├── .env                      # VITE_RAZORPAY_KEY_ID (git-ignored)
    │
    └── src/
        ├── main.tsx              # React entry point
        ├── App.tsx               # Root component, routing logic
        │
        ├── components/
        │   ├── Login.tsx             # Biometric + password login UI
        │   ├── DashboardWrapper.tsx  # Role-based dashboard switcher
        │   ├── BuyerDashboard.tsx    # Search, cart, checkout UI
        │   ├── SellerDashboard.tsx   # Inventory management UI
        │   ├── ProductCard.tsx       # Individual product display
        │   └── BarcodeScanner.tsx    # html5-qrcode camera component
        │
        ├── hooks/
        │   └── useRazorpayCheckout.ts   # Exception-safe payment hook
        │
        ├── context/
        │   └── AppContext.tsx           # Global auth + cart state
        │
        └── types/
            └── razorpay.d.ts            # Razorpay SDK type declarations
```

---

## ⚙️ Local Setup & Installation

### Prerequisites

- Python **3.10+**
- Node.js **18+**
- PostgreSQL **14+** (local or Docker)
- A C++ build toolchain for `dlib` (required by `face_recognition`)

| OS | Command |
|---|---|
| **Windows** | Install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) → select "Desktop development with C++" |
| **macOS** | `xcode-select --install` |
| **Linux** | `sudo apt install build-essential cmake` |

---

### 1 — Clone the Repository

```bash
git clone https://github.com/your-username/Smarter-Blinkit-2.0.git
cd Smarter-Blinkit-2.0
```

### 2 — Backend: Python Virtual Environment

```bash
cd backend

# Create the virtual environment
python -m venv venv

# Activate — Windows CMD
venv\Scripts\activate

# Activate — Windows PowerShell
venv\Scripts\Activate.ps1

# Activate — macOS / Linux
source venv/bin/activate

# Install all pinned dependencies
pip install -r requirements.txt
```

> **Heads up:** `face_recognition` compiles `dlib` from source. First install takes 5–10 minutes. Make sure your C++ toolchain is ready before running `pip install`.

### 3 — Frontend: Node Modules

```bash
cd ../frontend
npm install
```

### 4 — Database Setup

```sql
-- Run in psql or any PostgreSQL client
CREATE DATABASE smartmarket;
```

Then seed the product catalog (from `backend/` with `venv` active):

```bash
# Import ~500 products from the BigBasket catalog
python seed_big_basket.py

# Optional: create test buyer/seller accounts
python seed_db.py
```

> Tables are created automatically on first server startup via `Base.metadata.create_all`.

---

## 🔑 Environment Variables

### Root `.env` — read by the FastAPI backend

```env
# PostgreSQL async connection string
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/smartmarket

# JWT signing secret — use a long random string in production
JWT_SECRET=your-super-secret-jwt-key-change-this

# Razorpay — get from dashboard.razorpay.com
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=your_razorpay_key_secret
```

### `frontend/.env` — read by Vite

```env
# Must be prefixed with VITE_ to be exposed to the browser bundle
VITE_RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
```

> Both files are covered by `.gitignore` and will never be committed.

---

## 🚀 Running the Application

### Start the FastAPI Backend

```bash
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

| | URL |
|---|---|
| REST API | `http://127.0.0.1:8000` |
| Swagger UI | `http://127.0.0.1:8000/docs` |
| ReDoc | `http://127.0.0.1:8000/redoc` |

### Start the React Frontend

Open a second terminal:

```bash
cd frontend
npm run dev
```

App available at **`http://localhost:5173`**

---

## 📡 API Reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | — | Register with face embedding + password |
| `POST` | `/api/auth/login` | — | Email + password login |
| `POST` | `/api/auth/face-login` | — | Biometric login via webcam frame |
| `GET` | `/api/products/search` | `Bearer` | Location-aware semantic product search |
| `GET` | `/api/seller/inventory` | `Bearer` seller | Fetch seller's full inventory |
| `PATCH` | `/api/seller/inventory/{id}` | `Bearer` seller | Update price or stock quantity |
| `PATCH` | `/api/inventory/update-by-barcode` | `Bearer` seller | Increment stock via barcode scan |
| `POST` | `/api/payments/create-order` | `Bearer` | Create Razorpay order from cart |
| `POST` | `/api/payments/verify` | `Bearer` | Verify HMAC signature + decrement stock |

---

## 🗺 Stage 2 Roadmap

- [ ] Real-time order tracking with WebSockets
- [ ] Seller analytics dashboard — revenue, top products, stock velocity
- [ ] AI-powered demand forecasting for inventory restocking alerts
- [ ] Multi-image product listings with CDN storage
- [ ] Push notifications for low-stock and order status updates
