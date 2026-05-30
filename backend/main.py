from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
from typing import Optional
import jwt
import os

from database import get_db, engine, Base
from models import ProductCatalog, SellerInventory, Shop, User
from utils import calculate_distance
from auth import router as auth_router

SECRET_KEY = os.getenv("JWT_SECRET", "fallback-dev-secret-change-in-production")
ALGORITHM  = "HS256"

app = FastAPI(title="Smart Marketplace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)

@app.on_event("startup")
async def startup_event():
    # In production, use Alembic migrations instead of create_all()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/api/products/search")
async def search_products(
    buyer_latitude: float = Query(..., description="Latitude of the buyer's location"),
    buyer_longitude: float = Query(..., description="Longitude of the buyer's location"),
    limit: int = Query(20, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    q: str | None = Query(None, description="Search term matched against product name and description"),
    category: str | None = Query(None, description="Filter by exact product category"),
    db: AsyncSession = Depends(get_db)
):
    try:
        # --- Bounding-box pre-filter ---
        # 1 degree of latitude  ≈ 111 km.
        # 1 degree of longitude ≈ 111 km * cos(lat) — at Jaipur (~27°N) that's ~99 km.
        # A ±0.5° box therefore covers roughly a 55 km radius, which is more than
        # enough for hyper-local fulfillment while eliminating the vast majority of
        # rows before the JOIN and Haversine calculation run in Python.
        BBOX_DEG = 0.5
        lat_min = buyer_latitude  - BBOX_DEG
        lat_max = buyer_latitude  + BBOX_DEG
        lon_min = buyer_longitude - BBOX_DEG
        lon_max = buyer_longitude + BBOX_DEG

        # Join seller inventory with the shared catalog + shop location.
        # Filters applied at the DB level (in order of selectivity):
        #   1. Bounding-box on Shop coordinates  — eliminates distant shops before JOIN
        #   2. stock_quantity > 0                — drops out-of-stock inventory rows
        #   3. Optional full-text search on name/description via ILIKE
        #   4. Optional exact category match
        stmt = (
            select(SellerInventory, ProductCatalog, Shop)
            .join(ProductCatalog, SellerInventory.product_catalog_id == ProductCatalog.id)
            .join(Shop, SellerInventory.shop_id == Shop.id)
            .where(
                Shop.latitude  >= lat_min,
                Shop.latitude  <= lat_max,
                Shop.longitude >= lon_min,
                Shop.longitude <= lon_max,
                SellerInventory.stock_quantity > 0,
            )
        )

        # Optional search term — case-insensitive match on name OR description
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    ProductCatalog.name.ilike(pattern),
                    ProductCatalog.description.ilike(pattern),
                )
            )

        # Optional category filter — case-insensitive exact match
        if category and category.strip():
            stmt = stmt.where(ProductCatalog.category.ilike(category.strip()))

        stmt = stmt.limit(limit).offset(offset)

        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return []

        products_with_distance = []
        for inventory, catalog, shop in rows:
            distance_km = calculate_distance(
                buyer_latitude,
                buyer_longitude,
                shop.latitude,
                shop.longitude,
            )
            products_with_distance.append(
                {
                    "inventory": inventory,
                    "catalog": catalog,
                    "shop": shop,
                    "distance": distance_km,
                }
            )

        products_with_distance.sort(key=lambda x: x["distance"])

        response = []
        for item in products_with_distance:
            inv = item["inventory"]
            cat = item["catalog"]
            shop = item["shop"]
            response.append(
                {
                    # Keep `id` as the concrete purchasable item (seller inventory row).
                    "id": inv.id,
                    "product_catalog_id": cat.id,
                    "name": cat.name,
                    "description": cat.description,
                    "category": cat.category,
                    "price": inv.price,
                    "stock_count": inv.stock_quantity,
                    "image_url": cat.image_url,
                    "shop": {
                        "id": shop.id,
                        "shop_name": shop.shop_name,
                        "latitude": shop.latitude,
                        "longitude": shop.longitude,
                        "distance_km": round(item["distance"], 2),
                    },
                }
            )

        return response
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch products: {str(e)}")


# ---------------------------------------------------------------------------
# Seller endpoints
# ---------------------------------------------------------------------------

from pydantic import BaseModel as PydanticBaseModel

class InventoryUpdateRequest(PydanticBaseModel):
    price: Optional[float] = None
    stock_quantity: Optional[int] = None


def _decode_seller_token(authorization: str) -> dict:
    """
    Extract and validate the JWT from the Authorization header.
    Raises HTTP 401 on any failure.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")
    if payload.get("role") != "seller":
        raise HTTPException(status_code=403, detail="Seller access required.")
    return payload


@app.get("/api/seller/inventory")
async def get_seller_inventory(
    authorization: str = Header(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return all SellerInventory rows for the authenticated seller's shop.
    If the seller has no shop yet, one is auto-created at MNIT Campus and
    seeded with a random sample of 300 rows from the existing ProductCatalog
    so the dashboard is never empty on first login.
    """
    payload = _decode_seller_token(authorization)
    user_id: int = payload["user_id"]
    print(f"[seller/inventory] user_id={user_id} email={payload.get('sub')}")

    # ── 1. Resolve shop ──────────────────────────────────────────────────────
    shop_result = await db.execute(select(Shop).where(Shop.owner_id == user_id))
    shop = shop_result.scalars().first()

    if shop is None:
        print(f"[seller/inventory] No shop found for user_id={user_id} — auto-creating.")

        shop = Shop(
            owner_id=user_id,
            shop_name=f"{payload.get('sub', 'My')} Shop",
            latitude=26.8631,   # MNIT Campus — within the Jaipur bounding box
            longitude=75.8106,
        )
        db.add(shop)
        await db.flush()   # get shop.id before we use it below
        print(f"[seller/inventory] Created shop id={shop.id}")

        # ── 2. Seed 300 random catalog rows into the new shop ────────────────
        catalog_result = await db.execute(
            select(ProductCatalog).order_by(ProductCatalog.id)
        )
        all_catalog = catalog_result.scalars().all()

        import random as _random
        sample = _random.sample(all_catalog, min(300, len(all_catalog)))
        print(f"[seller/inventory] Seeding {len(sample)} inventory rows for new shop.")

        for cat in sample:
            db.add(SellerInventory(
                product_catalog_id=cat.id,
                shop_id=shop.id,
                price=round(_random.uniform(10.0, 500.0), 2),
                stock_quantity=_random.randint(10, 250),
            ))

        await db.commit()
        print(f"[seller/inventory] Seed complete for shop id={shop.id}")
    else:
        print(f"[seller/inventory] Found shop id={shop.id} name='{shop.shop_name}'")

    # ── 3. Fetch inventory ───────────────────────────────────────────────────
    inv_result = await db.execute(
        select(SellerInventory, ProductCatalog)
        .join(ProductCatalog, SellerInventory.product_catalog_id == ProductCatalog.id)
        .where(SellerInventory.shop_id == shop.id)
        .order_by(ProductCatalog.name)
    )
    rows = inv_result.all()
    print(f"[seller/inventory] Returning {len(rows)} inventory rows for shop id={shop.id}")

    inventory = [
        {
            "inventory_id":       inv.id,
            "product_catalog_id": cat.id,
            "name":               cat.name,
            "category":           cat.category,
            "image_url":          cat.image_url,
            "price":              inv.price,
            "stock_quantity":     inv.stock_quantity,
            "status": (
                "Out of Stock" if inv.stock_quantity == 0
                else "Low Stock"  if inv.stock_quantity <= 20
                else "In Stock"
            ),
        }
        for inv, cat in rows
    ]

    low_stock_count = sum(
        1 for item in inventory
        if 0 < item["stock_quantity"] <= 20
    )

    return {
        "shop": {
            "id":        shop.id,
            "shop_name": shop.shop_name,
            "latitude":  shop.latitude,
            "longitude": shop.longitude,
        },
        "inventory": inventory,
        "stats": {
            "total_products":  len(inventory),
            "low_stock_count": low_stock_count,
        },
    }


@app.patch("/api/seller/inventory/{inventory_id}")
async def update_inventory_item(
    inventory_id: int,
    body: InventoryUpdateRequest,
    authorization: str = Header(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Update price and/or stock_quantity for a single SellerInventory row.
    Only the owning seller may update their own rows.
    """
    payload = _decode_seller_token(authorization)
    user_id: int = payload["user_id"]

    # Fetch the inventory row and verify ownership in one query
    stmt = (
        select(SellerInventory, Shop)
        .join(Shop, SellerInventory.shop_id == Shop.id)
        .where(
            SellerInventory.id == inventory_id,
            Shop.owner_id == user_id,
        )
    )
    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Inventory item not found or does not belong to your shop.",
        )

    inv, _ = row

    if body.price is not None:
        if body.price < 0:
            raise HTTPException(status_code=422, detail="Price cannot be negative.")
        inv.price = body.price

    if body.stock_quantity is not None:
        if body.stock_quantity < 0:
            raise HTTPException(status_code=422, detail="Stock quantity cannot be negative.")
        inv.stock_quantity = body.stock_quantity

    await db.commit()
    await db.refresh(inv)

    return {
        "inventory_id":   inv.id,
        "price":          inv.price,
        "stock_quantity": inv.stock_quantity,
        "status": (
            "Out of Stock" if inv.stock_quantity == 0
            else "Low Stock"  if inv.stock_quantity <= 20
            else "In Stock"
        ),
    }


# ---------------------------------------------------------------------------
# Feature 1 — Barcode-based stock increment
# ---------------------------------------------------------------------------

class BarcodeScanRequest(PydanticBaseModel):
    barcode: str


@app.patch("/api/inventory/update-by-barcode")
async def update_stock_by_barcode(
    body: BarcodeScanRequest,
    authorization: str = Header(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Increment stock_quantity by 1 for the SellerInventory row whose
    ProductCatalog description contains the scanned barcode string,
    scoped to the authenticated seller's shop.

    Matching strategy (in order):
      1. Exact match on ProductCatalog.description containing the barcode
      2. Exact match on ProductCatalog.name containing the barcode
    This is intentionally loose so it works with both EAN-13 barcodes
    embedded in the BigBasket description field and manual test scans.
    """
    payload  = _decode_seller_token(authorization)
    user_id: int = payload["user_id"]
    barcode  = body.barcode.strip()

    print(f"[barcode-scan] user_id={user_id} barcode={barcode}")

    # Resolve seller's shop
    shop_result = await db.execute(select(Shop).where(Shop.owner_id == user_id))
    shop = shop_result.scalars().first()
    if not shop:
        raise HTTPException(status_code=404, detail="No shop found for this seller.")

    # Find the matching inventory row (scoped to this shop)
    stmt = (
        select(SellerInventory, ProductCatalog)
        .join(ProductCatalog, SellerInventory.product_catalog_id == ProductCatalog.id)
        .where(
            SellerInventory.shop_id == shop.id,
            or_(
                ProductCatalog.description.ilike(f"%{barcode}%"),
                ProductCatalog.name.ilike(f"%{barcode}%"),
            ),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No product found in your inventory matching barcode '{barcode}'.",
        )

    inv, cat = row
    inv.stock_quantity += 1
    await db.commit()
    await db.refresh(inv)

    print(f"[barcode-scan] Updated inventory_id={inv.id} '{cat.name}' → stock={inv.stock_quantity}")

    return {
        "barcode":            barcode,
        "inventory_id":       inv.id,
        "product_name":       cat.name,
        "new_stock_quantity": inv.stock_quantity,
    }


# ---------------------------------------------------------------------------
# Feature 2 — Razorpay dummy payment
# ---------------------------------------------------------------------------

import hmac
import hashlib
import uuid

# Razorpay test credentials — replace with real keys from dashboard.razorpay.com
RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID",     "rzp_test_placeholder")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "test_secret_placeholder")


class OrderItem(PydanticBaseModel):
    inventory_id:       str
    product_catalog_id: str
    shop_id:            str
    name:               str
    price:              float
    quantity:           int


class CreateOrderRequest(PydanticBaseModel):
    items: list[OrderItem]


class VerifyPaymentRequest(PydanticBaseModel):
    razorpay_order_id:   str
    razorpay_payment_id: str
    razorpay_signature:  str
    # Cart items forwarded from the frontend so we can decrement stock
    # in the same request that verifies the signature.
    items: list[OrderItem] = []


def _decode_buyer_token(authorization: str) -> dict:
    """JWT decoder that accepts both buyer and seller roles."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1]
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


@app.post("/api/payments/create-order")
async def create_payment_order(
    body: CreateOrderRequest,
    authorization: str = Header(..., alias="Authorization"),
):
    """
    Calculate the cart total and return a mock Razorpay order object.

    In production this would call razorpay.order.create() via the Razorpay
    Python SDK. In test/demo mode we generate a deterministic fake order_id
    so the frontend can open the Razorpay modal without a live API key.
    """
    _decode_buyer_token(authorization)

    if not body.items:
        raise HTTPException(status_code=422, detail="Cart is empty.")

    # Total in paise (1 INR = 100 paise)
    total_inr   = sum(item.price * item.quantity for item in body.items)
    total_paise = int(round(total_inr * 100))

    # In production: use razorpay.Client and call orders.create(...)
    # Here we generate a stable fake order_id for test mode.
    fake_order_id = f"order_{uuid.uuid4().hex[:16]}"

    print(f"[payments/create-order] total=₹{total_inr:.2f}  order_id={fake_order_id}")

    return {
        "razorpay_order_id": fake_order_id,
        "amount":            total_paise,
        "currency":          "INR",
    }


@app.post("/api/payments/verify")
async def verify_payment(
    body: VerifyPaymentRequest,
    authorization: str = Header(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    1. Verify the Razorpay HMAC-SHA256 signature.
    2. Inside a single DB transaction, decrement stock_quantity for every
       purchased SellerInventory row by the purchased quantity.
    3. Return a unified success payload.

    Signature verification:
        expected = HMAC_SHA256(order_id + "|" + payment_id, key_secret)

    In test/demo mode (placeholder secret) the signature check is bypassed
    so the full flow works without a live Razorpay account.

    All database logic is wrapped in try/except so any column type mismatch,
    bad transaction commit, or unexpected DB error returns a structured JSON
    400 response instead of a silent 500 — allowing the frontend to unlock
    the cart immediately rather than hanging on "Processing...".
    """
    _decode_buyer_token(authorization)

    # ── 1. Signature verification ────────────────────────────────────────────
    expected_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    signature_valid = hmac.compare_digest(expected_signature, body.razorpay_signature)
    is_test_mode    = RAZORPAY_KEY_SECRET == "test_secret_placeholder"

    if not signature_valid and not is_test_mode:
        raise HTTPException(status_code=400, detail="Payment signature verification failed.")

    print(
        f"[payments/verify] order={body.razorpay_order_id} "
        f"payment={body.razorpay_payment_id} "
        f"sig_valid={signature_valid} test_mode={is_test_mode} "
        f"items={len(body.items)}"
    )

    # ── 2. Decrement stock for each purchased item ───────────────────────────
    # Wrapped in try/except so any DB-level failure (type mismatch, constraint
    # violation, failed commit, etc.) is caught, logged, and returned as a
    # structured JSON error — never a silent 500 that leaves the cart locked.
    stock_updates: list[dict] = []

    try:
        if body.items:
            for item in body.items:
                try:
                    inv_id = int(item.inventory_id)
                except (ValueError, TypeError):
                    print(f"[payments/verify] Skipping invalid inventory_id={item.inventory_id!r}")
                    continue

                result = await db.execute(
                    select(SellerInventory).where(SellerInventory.id == inv_id)
                )
                inv = result.scalars().first()

                if inv is None:
                    print(f"[payments/verify] inventory_id={inv_id} not found — skipping")
                    continue

                # Clamp at zero — never go negative
                deduct             = min(item.quantity, inv.stock_quantity)
                inv.stock_quantity -= deduct

                stock_updates.append({
                    "inventory_id":       inv.id,
                    "quantity_deducted":  deduct,
                    "new_stock_quantity": inv.stock_quantity,
                })

                print(
                    f"[payments/verify] inventory_id={inv.id} "
                    f"deducted={deduct} remaining={inv.stock_quantity}"
                )

            # Commit all stock changes atomically
            await db.commit()

        print(f"[payments/verify] Stock updated for {len(stock_updates)} item(s). Payment complete.")

        return {
            "status":        "success",
            "message":       "Payment verified and inventory updated.",
            "payment_id":    body.razorpay_payment_id,
            "stock_updates": stock_updates,
        }

    except Exception as e:
        # Roll back any partial changes so the DB stays consistent
        await db.rollback()
        print(f"[payments/verify] Backend Error: {e}")
        # Return a 400 with a structured JSON body so the frontend can parse
        # the error message and unlock the cart immediately.
        raise HTTPException(
            status_code=400,
            detail=f"Inventory update failed: {str(e)}",
        )
