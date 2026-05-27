import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine, AsyncSessionLocal, Base
from models import User, Shop, Product, RoleEnum

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
            latitude=28.7041,
            longitude=77.1025
        )
        session.add(shop)
        await session.flush()  # Flush to get the shop ID
        
        # Create diverse realistic products
        products = [
            Product(
                shop_id=shop.id,
                name="Amul Taaza Toned Milk (1L)",
                description="Fresh toned milk packed with nutrients.",
                price=68.0,
                stock_count=50,
                barcode_string="8901262150117",
                image_url="https://example.com/milk.jpg"
            ),
            Product(
                shop_id=shop.id,
                name="Britannia NutriChoice Digestive Biscuits (100g)",
                description="Healthy digestive biscuits with whole wheat.",
                price=30.0,
                stock_count=120,
                barcode_string="8901063013217",
                image_url="https://example.com/biscuits.jpg"
            ),
            Product(
                shop_id=shop.id,
                name="Maggi 2-Minute Noodles (70g)",
                description="Instant noodles, the classic Indian snack.",
                price=14.0,
                stock_count=300,
                barcode_string="8901058141257",
                image_url="https://example.com/maggi.jpg"
            ),
            Product(
                shop_id=shop.id,
                name="Surf Excel Easy Wash Detergent Powder (1kg)",
                description="Tough stain removal powder.",
                price=135.0,
                stock_count=20,
                barcode_string="8901030588665",
                image_url="https://example.com/detergent.jpg"
            ),
            Product(
                shop_id=shop.id,
                name="Aashirvaad Shudh Chakki Atta (5kg)",
                description="100% whole wheat atta.",
                price=240.0,
                stock_count=45,
                barcode_string="8901725132204",
                image_url="https://example.com/atta.jpg"
            )
        ]
        
        session.add_all(products)
        await session.commit()
        
        print(f"Successfully inserted {len(products)} products into the shop '{shop.shop_name}' owned by '{seller.name}'.")

if __name__ == "__main__":
    asyncio.run(seed_data())
