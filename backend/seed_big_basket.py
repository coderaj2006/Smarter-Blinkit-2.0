import asyncio
import csv
import random
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from database import engine, AsyncSessionLocal, Base
from models import ProductCatalog, RoleEnum, SellerInventory, Shop, User


CSV_PATH = Path(__file__).with_name("BigBasket.csv")

# ---------------------------------------------------------------------------
# Configuration — set this to your registered seller's email before running.
# The script will look up this user in the database and assign
# REAL_SELLER_PRODUCT_COUNT inventory rows directly to their shop.
# ---------------------------------------------------------------------------
REAL_SELLER_EMAIL = "abcxyz@gmail.com"          # registered seller account
REAL_SELLER_PRODUCT_COUNT = 300                 # how many BigBasket rows to assign to your shop


def parse_price(value: object) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Be tolerant of "₹", commas, and whitespace.
    s = s.replace("₹", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


async def seed_big_basket():
    print("Initializing database schema...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database schema created or verified.")

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found at: {CSV_PATH}")

    jaipur_shops = [
        # Around Jaipur, Rajasthan (approx). Includes MNIT area and common neighborhoods.
        {"shop_name": "Jaipur QuickMart - MNIT",          "latitude": 26.8631, "longitude": 75.8106},
        {"shop_name": "Jaipur QuickMart - Malviya Nagar", "latitude": 26.8546, "longitude": 75.8243},
        {"shop_name": "Jaipur QuickMart - Raja Park",     "latitude": 26.8944, "longitude": 75.8273},
        {"shop_name": "Jaipur QuickMart - Vaishali Nagar","latitude": 26.9124, "longitude": 75.7367},
        {"shop_name": "Jaipur QuickMart - Mansarovar",    "latitude": 26.8467, "longitude": 75.7696},
    ]

    async with AsyncSessionLocal() as session:

        # ----------------------------------------------------------------
        # 1. Resolve the real registered seller (if the email exists)
        # ----------------------------------------------------------------
        real_seller_shop: Optional[Shop] = None

        real_seller_result = await session.execute(
            select(User).where(User.email == REAL_SELLER_EMAIL)
        )
        real_seller = real_seller_result.scalars().first()

        if real_seller is None:
            print(
                f"[WARN] No user found with email '{REAL_SELLER_EMAIL}'.\n"
                f"       Update REAL_SELLER_EMAIL at the top of this script to match\n"
                f"       your registered account, then re-run.\n"
                f"       Continuing without assigning rows to a real seller."
            )
        elif real_seller.role != RoleEnum.seller:
            print(
                f"[WARN] User '{REAL_SELLER_EMAIL}' exists but has role '{real_seller.role.value}', not 'seller'.\n"
                f"       Skipping real-seller assignment."
            )
        else:
            # Look for an existing shop owned by this seller
            existing_real_shops = (
                await session.execute(select(Shop).where(Shop.owner_id == real_seller.id))
            ).scalars().all()

            if existing_real_shops:
                real_seller_shop = existing_real_shops[0]
                print(
                    f"[INFO] Found existing shop '{real_seller_shop.shop_name}' "
                    f"(id={real_seller_shop.id}) for seller '{REAL_SELLER_EMAIL}'."
                )
            else:
                # Seller has no shop yet — create one at MNIT Campus coordinates
                real_seller_shop = Shop(
                    owner_id=real_seller.id,
                    shop_name="My Shop",
                    latitude=26.8631,
                    longitude=75.8106,
                )
                session.add(real_seller_shop)
                await session.flush()
                print(
                    f"[INFO] Created new shop 'My Shop' (id={real_seller_shop.id}) "
                    f"for seller '{REAL_SELLER_EMAIL}' at MNIT Campus coordinates."
                )

        # ----------------------------------------------------------------
        # 2. Create or reuse the mock seller + 5 Jaipur shops
        # ----------------------------------------------------------------
        mock_seller_email = "jaipur-seller@example.com"
        existing_mock_seller = (
            await session.execute(select(User).where(User.email == mock_seller_email))
        ).scalars().first()

        if existing_mock_seller:
            mock_seller = existing_mock_seller
        else:
            mock_seller = User(
                name="Jaipur Seller",
                email=mock_seller_email,
                hashed_password="hashed_placeholder",
                role=RoleEnum.seller,
            )
            session.add(mock_seller)
            await session.flush()

        existing_mock_shops = (
            await session.execute(select(Shop).where(Shop.owner_id == mock_seller.id))
        ).scalars().all()
        existing_mock_shop_names = {s.shop_name for s in existing_mock_shops}

        mock_shops: list[Shop] = []
        for s in jaipur_shops:
            if s["shop_name"] in existing_mock_shop_names:
                shop = next(x for x in existing_mock_shops if x.shop_name == s["shop_name"])
            else:
                shop = Shop(
                    owner_id=mock_seller.id,
                    shop_name=s["shop_name"],
                    latitude=float(s["latitude"]),
                    longitude=float(s["longitude"]),
                )
                session.add(shop)
                await session.flush()
            mock_shops.append(shop)

        # ----------------------------------------------------------------
        # 3. Build the full pool of shops to distribute inventory across.
        #    The real seller's shop is included so it gets real rows.
        # ----------------------------------------------------------------
        all_shops = list(mock_shops)
        if real_seller_shop is not None:
            all_shops.append(real_seller_shop)

        # ----------------------------------------------------------------
        # 4. Read the CSV and seed catalog + inventory rows
        # ----------------------------------------------------------------
        existing_catalog_names = set(
            (await session.execute(select(ProductCatalog.name))).scalars().all()
        )

        inserted            = 0
        skipped_duplicates  = 0
        skipped_bad_rows    = 0

        # We'll collect all valid parsed rows first so we can shuffle them
        # and guarantee the real seller gets exactly REAL_SELLER_PRODUCT_COUNT rows.
        parsed_rows: list[dict] = []

        with CSV_PATH.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            required_cols = {
                "ProductName", "Brand", "Price", "DiscountPrice",
                "Image_Url", "Quantity", "Category", "SubCategory", "Absolute_Url",
            }
            missing = required_cols - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV missing expected columns: {sorted(missing)}")

            for row in reader:
                product_name  = (row.get("ProductName") or "").strip()
                qty           = (row.get("Quantity") or "").strip()
                brand         = (row.get("Brand") or "").strip()
                category      = (row.get("Category") or "").strip()
                sub_category  = (row.get("SubCategory") or "").strip()
                image_url     = (row.get("Image_Url") or "").strip() or None
                absolute_url  = (row.get("Absolute_Url") or "").strip() or None

                if not product_name:
                    skipped_bad_rows += 1
                    continue

                catalog_name = f"{product_name} ({qty})" if qty else product_name

                price = parse_price(row.get("DiscountPrice")) or parse_price(row.get("Price"))
                if price is None:
                    skipped_bad_rows += 1
                    continue

                description_parts = [
                    p for p in [
                        brand,
                        " / ".join(p for p in [category, sub_category] if p) or None,
                        qty,
                        absolute_url,
                    ] if p
                ]
                description = " • ".join(description_parts) if description_parts else None

                parsed_rows.append({
                    "catalog_name": catalog_name,
                    "description":  description,
                    "category":     category or None,
                    "image_url":    image_url,
                    "price":        float(price),
                })

        # Shuffle so the real-seller slice is a random cross-section of categories
        random.shuffle(parsed_rows)

        # Determine which row indices go to the real seller's shop
        real_seller_indices: set[int] = set()
        if real_seller_shop is not None:
            count = min(REAL_SELLER_PRODUCT_COUNT, len(parsed_rows))
            real_seller_indices = set(range(count))
            print(
                f"[INFO] Assigning {count} rows to your shop "
                f"'{real_seller_shop.shop_name}' (id={real_seller_shop.id})."
            )

        for idx, row in enumerate(parsed_rows):
            catalog_name = row["catalog_name"]

            # Resolve or create the catalog entry
            if catalog_name not in existing_catalog_names:
                catalog = ProductCatalog(
                    name=catalog_name,
                    description=row["description"],
                    category=row["category"],
                    image_url=row["image_url"],
                )
                session.add(catalog)
                await session.flush()
                existing_catalog_names.add(catalog_name)
            else:
                catalog = (
                    await session.execute(
                        select(ProductCatalog).where(ProductCatalog.name == catalog_name)
                    )
                ).scalars().first()
                if catalog is None:
                    skipped_bad_rows += 1
                    continue
                skipped_duplicates += 1

            # Assign to the real seller's shop for the first N rows,
            # otherwise distribute randomly across mock shops.
            if idx in real_seller_indices:
                target_shop = real_seller_shop
            else:
                target_shop = random.choice(mock_shops)

            inventory = SellerInventory(
                product_catalog_id=catalog.id,
                shop_id=target_shop.id,
                price=row["price"],
                stock_quantity=random.randint(10, 250),
            )
            session.add(inventory)
            inserted += 1

            if inserted % 500 == 0:
                await session.commit()
                print(f"  Inserted {inserted} inventory rows so far...")

        await session.commit()

        real_seller_count = len(real_seller_indices) if real_seller_shop else 0
        print("\nDone.")
        print(f"  Total inventory rows inserted : {inserted}")
        print(f"  Assigned to your real shop    : {real_seller_count}")
        print(f"  Assigned to mock shops        : {inserted - real_seller_count}")
        print(f"  Skipped (duplicate catalog)   : {skipped_duplicates}")
        print(f"  Skipped (bad/empty rows)      : {skipped_bad_rows}")
        print(f"  Shops in pool                 : {len(all_shops)}")


if __name__ == "__main__":
    asyncio.run(seed_big_basket())


