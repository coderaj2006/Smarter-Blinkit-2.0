import asyncio
from database import engine, AsyncSessionLocal, Base
from models import ProductCatalog, RoleEnum, SellerInventory, Shop, User

async def seed_data():
    print("Initializing database schema...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("Database schema created or verified.")
    print("Seeding data...")
    
    async with AsyncSessionLocal() as session:
        # Create a sample seller
        seller = User(
            name="Sample Seller",
            email="seller@example.com",
            hashed_password="hashed_placeholder",
            role=RoleEnum.seller
        )
        session.add(seller)
        await session.flush()  # Flush to get the seller ID
        
        # Create a sample shop
        shop = Shop(
            owner_id=seller.id,
            shop_name="Blinkit SuperMart",
            latitude=28.6200,
            longitude=77.2050
        )
        session.add(shop)
        await session.flush()  # Flush to get the shop ID
        
        # Create diverse realistic catalog products + seller inventory rows
        catalog_rows = [
            ProductCatalog(
                name="Amul Taaza Toned Milk (1L)",
                description="Fresh toned milk packed with nutrients.",
                category="Dairy",
                image_url="https://example.com/milk.jpg",
            ),
            ProductCatalog(
                name="Britannia NutriChoice Digestive Biscuits (100g)",
                description="Healthy digestive biscuits with whole wheat.",
                category="Snacks",
                image_url="https://example.com/biscuits.jpg",
            ),
            ProductCatalog(
                name="Maggi 2-Minute Noodles (70g)",
                description="Instant noodles, the classic Indian snack.",
                category="Instant Food",
                image_url="https://example.com/maggi.jpg",
            ),
            ProductCatalog(
                name="Surf Excel Easy Wash Detergent Powder (1kg)",
                description="Tough stain removal powder.",
                category="Cleaning",
                image_url="https://example.com/detergent.jpg",
            ),
            ProductCatalog(
                name="Aashirvaad Shudh Chakki Atta (5kg)",
                description="100% whole wheat atta.",
                category="Staples",
                image_url="https://example.com/atta.jpg",
            ),
        ]

        session.add_all(catalog_rows)
        await session.flush()

        inventory_rows = [
            SellerInventory(product_catalog_id=catalog_rows[0].id, shop_id=shop.id, price=68.0, stock_quantity=50),
            SellerInventory(product_catalog_id=catalog_rows[1].id, shop_id=shop.id, price=30.0, stock_quantity=120),
            SellerInventory(product_catalog_id=catalog_rows[2].id, shop_id=shop.id, price=14.0, stock_quantity=300),
            SellerInventory(product_catalog_id=catalog_rows[3].id, shop_id=shop.id, price=135.0, stock_quantity=20),
            SellerInventory(product_catalog_id=catalog_rows[4].id, shop_id=shop.id, price=240.0, stock_quantity=45),
        ]

        session.add_all(inventory_rows)
        await session.commit()
        
        print(
            f"Successfully inserted {len(inventory_rows)} inventory items for shop '{shop.shop_name}' owned by '{seller.name}'."
        )

if __name__ == "__main__":
    asyncio.run(seed_data())
