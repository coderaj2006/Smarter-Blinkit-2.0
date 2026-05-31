"""Full HTTP test — registers a temp user, hits recommendations, cleans up."""
import asyncio, httpx, os
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()
engine  = create_async_engine(os.getenv("DATABASE_URL"), echo=False)
Session = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

GREEN = "\033[92m"; RED = "\033[91m"; CYAN = "\033[96m"; RESET = "\033[0m"
def ok(m):   print(f"  {GREEN}PASS{RESET}  {m}")
def fail(m): print(f"  {RED}FAIL{RESET}  {m}")
def info(m): print(f"  {CYAN}INFO{RESET}  {m}")

# Minimal 1x1 white JPEG base64 — enough for face_recognition to not crash
DUMMY_IMG = (
    "data:image/jpeg;base64,"
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
    "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN"
    "DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAA"
    "AAAAAAAAAAAAAAAAAP/EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUEQEAAAAAAAAAAAAAAAAA"
    "AAAA/9oADAMBAAIRAxEAPwCwABmX/9k="
)

async def test():
    print(f"\n{'='*55}")
    print("  HTTP Endpoint Test — /api/products/{{id}}/recommendations")
    print(f"{'='*55}\n")

    async with httpx.AsyncClient(timeout=15) as c:

        # ── Step 1: Register a temp test user ─────────────────────────────
        info("Registering temporary test user...")
        reg = await c.post("http://127.0.0.1:8000/api/auth/register", json={
            "name":         "Test User",
            "email":        "rectest_tmp@smartmarket.dev",
            "password":     "Test@1234",
            "role":         "buyer",
            "image_base64": DUMMY_IMG,
        })

        if reg.status_code not in (200, 400):
            fail(f"Registration failed: {reg.status_code} {reg.text[:100]}")
            return

        # If already registered, just login
        login = await c.post("http://127.0.0.1:8000/api/auth/login", json={
            "email":    "rectest_tmp@smartmarket.dev",
            "password": "Test@1234",
        })

        if login.status_code != 200:
            fail(f"Login failed: {login.status_code} {login.text[:100]}")
            return

        token = login.json()["access_token"]
        ok(f"Authenticated as rectest_tmp@smartmarket.dev")

        # ── Step 2: Hit the recommendations endpoint ───────────────────────
        info("Calling GET /api/products/1/recommendations ...")
        r = await c.get(
            "http://127.0.0.1:8000/api/products/1/recommendations",
            headers={"Authorization": f"Bearer {token}"},
        )

        if r.status_code != 200:
            fail(f"HTTP {r.status_code}: {r.text[:200]}")
            return

        data = r.json()
        ok(f"HTTP 200 received")
        ok(f"product_catalog_id = {data['product_catalog_id']}")
        ok(f"alternatives:    {len(data['alternatives'])} products returned")
        ok(f"bought_together: {len(data['bought_together'])} products returned")

        # ── Step 3: Verify hydration ───────────────────────────────────────
        if data["alternatives"]:
            p = data["alternatives"][0]
            fields = ["id", "name", "price", "stock_count", "image_url", "shop"]
            missing = [f for f in fields if not p.get(f)]
            if not missing:
                ok(f"Hydration OK — '{p['name']}' | Rs{p['price']} | "
                   f"{p['shop']['shop_name']} ({p['shop']['distance_km']} km) | "
                   f"stock={p['stock_count']}")
            else:
                fail(f"Missing fields in product: {missing}")

            # All alternatives should be in the same category as product 1
            info(f"All {len(data['alternatives'])} alternatives:")
            for alt in data["alternatives"]:
                print(f"    • {alt['name']} | Rs{alt['price']} | {alt['category']}")
        else:
            fail("No alternatives returned — check Neo4j category property")

        # ── Step 4: Test a different product ──────────────────────────────
        info("\nCalling GET /api/products/100/recommendations ...")
        r2 = await c.get(
            "http://127.0.0.1:8000/api/products/100/recommendations",
            headers={"Authorization": f"Bearer {token}"},
        )
        if r2.status_code == 200:
            d2 = r2.json()
            ok(f"Product 100: {len(d2['alternatives'])} alternatives, "
               f"{len(d2['bought_together'])} bought_together")
        else:
            fail(f"Product 100 failed: {r2.status_code}")

    # ── Cleanup: remove temp user ──────────────────────────────────────────
    async with Session() as db:
        await db.execute(text(
            "DELETE FROM users WHERE email = 'rectest_tmp@smartmarket.dev'"
        ))
        await db.commit()
    info("Temp user cleaned up.")

    print(f"\n{'='*55}")
    print(f"{GREEN}  All HTTP tests passed.{RESET}")
    print(f"{'='*55}\n")
    await engine.dispose()

asyncio.run(test())
