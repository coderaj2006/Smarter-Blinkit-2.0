# SmartMarket — Smarter Blinkit 2.0

> **An AI-driven, location-aware local commerce platform** that connects buyers to the nearest verified sellers using biometric authentication, semantic product search, and a real-time inventory pipeline — all within 10 km.

<br/>

<div align="center">

![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-6.0-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-3.4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-5.x-008CC1?style=for-the-badge&logo=neo4j&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLaMA3-F55036?style=for-the-badge&logoColor=white)

</div>

---

## Table of Contents

- [Key Features](#-key-features)
- [Tech Stack](#-tech-stack)
- [Graph Database Architecture](#-graph-database-architecture--relationships)
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

<br/>

### 🤖 Groq-Powered AI Recipe Agent
A natural-language shopping assistant that converts any meal intent or health query into a ready-to-buy ingredient list in under a second.

- Powered by **Groq API** running `llama-3.1-8b-instant` — the fastest publicly available LLM inference engine, delivering sub-200 ms parse times
- Uses `response_format={"type": "json_object"}` to enforce strict structured output — the model returns `{"ingredients": [...]}` with no markdown, no prose, no parsing ambiguity
- Intent-aware system prompt handles recipes ("Make lasagna for 3"), health queries ("I have a cold"), cravings ("something sweet"), and moods — not just ingredient extraction
- Falls back gracefully to a naive tokeniser if the API key is absent, keeping the endpoint functional in offline/dev environments

<br/>

### 🌐 Global Database Inventory Scan
The AI agent searches the entire product catalog without any of the restrictions applied to the paginated browse endpoint.

- For every ingredient extracted by the LLM, a dedicated SQLAlchemy query joins `SellerInventory → ProductCatalog → Shop` across the **entire database** — no `LIMIT`, no `OFFSET`, no ±0.5° bounding box
- All ingredient queries fire **concurrently** via `asyncio.gather`, so a 10-ingredient recipe resolves in roughly the time of a single query rather than 10×
- From all in-stock candidates per ingredient, **Haversine great-circle distance** is computed against the buyer's coordinates and the single closest seller is selected
- A minimum cosine similarity threshold (0.40) filters out semantically irrelevant matches before the distance sort runs, preventing nonsense results like "shower gel" for "headache"

<br/>

### 🧠 Semantic Embedding Search
Product matching uses meaning, not character patterns — "cold drink" finds iced tea and coconut water, not just products with "cold" in the name.

- Every product name in the catalog is encoded into a **384-dimensional vector** using `all-MiniLM-L6-v2` (sentence-transformers) and stored as a native PostgreSQL `FLOAT[]` column — no pgvector extension required
- At query time, the ingredient term is embedded and **batch cosine similarity** is computed against all 8 000+ product vectors in a single `numpy` matrix multiplication (~20 ms)
- The embedding cache is loaded into memory once at server startup and reused for all subsequent requests — zero per-request DB overhead for the similarity computation
- Falls back to ILIKE lexical matching if embeddings haven't been generated yet, so the endpoint always returns something useful

<br/>

### 🕸 Neo4j Graph Recommendation Engine
A graph database layer that models product relationships for real-time cross-sell and alternative suggestions.

- **Alternatives** — products in the same category are surfaced via a Cypher query on the `category` property, giving buyers substitute options when an item is low or out of stock
- **Frequently Bought Together** — `BOUGHT_WITH` directed edges between product nodes are created and weight-incremented automatically every time a checkout completes, building a co-purchase graph that improves with every transaction
- Both recommendation lists are hydrated from PostgreSQL after Neo4j returns the catalog IDs, so the frontend receives fully populated product objects (price, image, shop, stock) — not just graph node IDs
- Neo4j is **optional** — if `NEO4J_PASSWORD` is left empty in `.env`, the server starts normally with recommendations returning empty arrays rather than crashing

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
| groq | 0.11.0 | Groq API client for LLM inference |
| sentence-transformers | 3.3.1 | all-MiniLM-L6-v2 semantic embeddings |
| neo4j | 5.20.0 | Async Neo4j graph database driver |

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
| PostgreSQL `ARRAY(Float)` | Native vector storage for face embeddings and product embeddings |
| Haversine formula | Great-circle distance calculation for store ranking |
| Groq API (`llama-3.1-8b-instant`) | Sub-200 ms natural language → structured JSON ingredient parsing |
| sentence-transformers (`all-MiniLM-L6-v2`) | 384-dim semantic product embeddings for meaning-based search |
| Neo4j 5 + Cypher | Graph database for `BOUGHT_WITH` and category-based `SIMILAR_TO` relationships |

---

## 🕸 Graph Database Architecture & Relationships

SmartMarket uses **Neo4j** as a dedicated graph layer alongside PostgreSQL. The two databases serve distinct roles — PostgreSQL owns all transactional data (users, inventory, orders), while Neo4j owns the relationship graph (product similarity, co-purchase patterns).

### Node Schema

```
(:Product {id: int, name: string, category: string})
```

Every `ProductCatalog` row from PostgreSQL is mirrored as a `:Product` node in Neo4j. The `id` property is the PostgreSQL primary key, which is used to JOIN back to SQL for data hydration after graph queries return results.

### Relationship 1 — Category Alternatives

```cypher
MATCH (p:Product {id: $id})
MATCH (alt:Product {category: p.category})
WHERE alt.id <> $id
RETURN alt.id AS id
LIMIT 6
```

Rather than pre-computing millions of `SIMILAR_TO` edges (which causes O(N²) edge explosion on large catalogs), alternatives are resolved at query time by matching on the shared `category` property. This gives the same result with zero storage overhead and no seeding time.

**Use case:** When a buyer views a product that is low or out of stock, the frontend can call `GET /api/products/{id}/recommendations` to surface 6 in-stock alternatives from the same category.

### Relationship 2 — Frequently Bought Together

```cypher
MATCH (a:Product {id: $id_a}), (b:Product {id: $id_b})
MERGE (a)-[r:BOUGHT_WITH]->(b)
ON CREATE SET r.weight = 1
ON MATCH  SET r.weight = r.weight + 1
```

Every time a checkout completes, `create_purchase_relationship()` is called as a **background task** for every distinct pair of items in the cart. The `BOUGHT_WITH` edge is created on first co-purchase and its `weight` is atomically incremented on every subsequent one — no batch jobs, no scheduled syncs.

Recommendations are then retrieved ordered by weight descending:

```cypher
MATCH (p:Product {id: $id})-[r:BOUGHT_WITH]->(together:Product)
RETURN together.id AS id
ORDER BY r.weight DESC
LIMIT 4
```

**Use case:** "Customers who bought this also bought..." — the classic market-basket cross-sell pattern, built automatically from real purchase behaviour.

### Seeding & Maintenance

| Script | Purpose | When to run |
|---|---|---|
| `seed_graph.py` | Creates all 8 000+ `:Product` nodes from PostgreSQL | Once after initial DB seed, or after Neo4j reset |
| `BOUGHT_WITH` edges | Auto-created at checkout via `create_purchase_relationship()` | Automatic — no manual step needed |

---

```
Smarter-Blinkit-2.0/
│
├── .env                          # Root secrets (DATABASE_URL, JWT_SECRET, Razorpay, Groq, Neo4j)
├── .gitignore
├── README.md
│
├── backend/
│   ├── main.py                   # FastAPI app — all route handlers
│   ├── auth.py                   # /api/auth/* — register, face-login, password-login
│   ├── agent.py                  # Groq LLM parsing + semantic ingredient resolution
│   ├── graph.py                  # Neo4j driver, sync utilities, recommendation queries
│   ├── models.py                 # ORM models: User, Shop, ProductCatalog, SellerInventory
│   ├── database.py               # Async engine, session factory, Base
│   ├── utils.py                  # Haversine distance calculation
│   ├── embed_products.py         # One-time: generate 384-dim embeddings for all products
│   ├── seed_graph.py             # One-time: populate Neo4j Product nodes from PostgreSQL
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
        │   ├── BuyerDashboard.tsx    # Search, AI agent tab, cart, checkout UI
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
- **Neo4j 5+** — [Neo4j Desktop](https://neo4j.com/download/) (free) or Docker: `docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/yourpassword neo4j:5`
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
# Import ~8000 products from the BigBasket catalog
python seed_big_basket.py

# Optional: create test buyer/seller accounts
python seed_db.py
```

> Tables are created automatically on first server startup via `Base.metadata.create_all`.

### 5 — Generate Semantic Embeddings (one-time)

```bash
# Encodes all product names into 384-dim vectors and stores them in PostgreSQL
# Downloads the all-MiniLM-L6-v2 model (~90 MB) on first run
python embed_products.py
```

> Safe to re-run — only products with a `NULL` embedding are processed.

### 6 — Seed the Neo4j Graph (one-time)

Start Neo4j Desktop (or Docker), then:

```bash
# Creates 8000+ :Product nodes in Neo4j from the PostgreSQL catalog
python seed_graph.py
```

> `BOUGHT_WITH` edges are built automatically at runtime as users complete purchases — no manual seeding needed.

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

# Groq AI — get a free key at https://console.groq.com → API Keys
# Model: llama-3.1-8b-instant (fastest) or llama-3.1-70b-versatile (most accurate)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
GROQ_MODEL=llama-3.1-8b-instant

# Neo4j Graph Database — leave NEO4J_PASSWORD empty to disable graph features
# Neo4j Desktop: set the password you chose when creating the local DBMS
# Docker: use the password from NEO4J_AUTH=neo4j/<password>
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password
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
| `POST` | `/api/agent/recipe` | `Bearer` | AI agent: natural language → ingredient shopping list |
| `GET` | `/api/products/{id}/recommendations` | `Bearer` | Neo4j: alternatives + bought-together suggestions |

---

## ✅ Stage 2 — Completed

- [x] Groq-powered AI recipe agent with structured JSON output
- [x] Global semantic inventory scan (no pagination restrictions)
- [x] 384-dim product embeddings with in-Python cosine similarity search
- [x] Neo4j graph layer — category alternatives + BOUGHT_WITH co-purchase edges
- [x] AI Smart Search tab in the buyer dashboard UI

## 🗺 Stage 3 Roadmap

- [ ] Real-time order tracking with WebSockets
- [ ] Seller analytics dashboard — revenue, top products, stock velocity
- [ ] AI-powered demand forecasting for inventory restocking alerts
- [ ] Multi-image product listings with CDN storage
- [ ] Push notifications for low-stock and order status updates
