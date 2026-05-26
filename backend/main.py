from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from database import get_db, engine, Base
from models import Product
from utils import calculate_distance

app = FastAPI(title="Smart Marketplace API")

@app.on_event("startup")
async def startup_event():
    # In production, use Alembic migrations instead of create_all()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/api/products/search")
async def search_products(
    buyer_latitude: float = Query(..., description="Latitude of the buyer's location"),
    buyer_longitude: float = Query(..., description="Longitude of the buyer's location"),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Fetch all products and eagerly load their associated shop
        stmt = select(Product).options(selectinload(Product.shop))
        result = await db.execute(stmt)
        products = result.scalars().all()

        if not products:
            return []

        products_with_distance = []
        for product in products:
            if not product.shop:
                continue
                
            # Calculate distance using Haversine utility
            distance_km = calculate_distance(
                buyer_latitude, 
                buyer_longitude, 
                product.shop.latitude, 
                product.shop.longitude
            )
            
            products_with_distance.append({
                "product": product,
                "distance": distance_km
            })

        # Sort products so closest shops appear first
        products_with_distance.sort(key=lambda x: x["distance"])

        # Format and return the response payload
        response = []
        for item in products_with_distance:
            p = item["product"]
            response.append({
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": p.price,
                "stock_count": p.stock_count,
                "barcode_string": p.barcode_string,
                "image_url": p.image_url,
                "shop": {
                    "id": p.shop.id,
                    "shop_name": p.shop.shop_name,
                    "latitude": p.shop.latitude,
                    "longitude": p.shop.longitude,
                    "distance_km": round(item["distance"], 2)
                }
            })

        return response
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch products: {str(e)}")
