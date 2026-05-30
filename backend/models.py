import enum
from sqlalchemy import Column, Integer, String, Float, Enum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from database import Base

class RoleEnum(str, enum.Enum):
    buyer = "buyer"
    seller = "seller"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(RoleEnum), nullable=False)
    face_embedding = Column(ARRAY(Float), nullable=True)

    shops = relationship("Shop", back_populates="owner", cascade="all, delete")

class Shop(Base):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shop_name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)

    owner = relationship("User", back_populates="shops")
    inventory_items = relationship("SellerInventory", back_populates="shop", cascade="all, delete")

class ProductCatalog(Base):
    """
    Unified product catalog (SKU-like) shared across all sellers.
    name_embedding: 384-dim vector from all-MiniLM-L6-v2, used for
    semantic similarity search in the AI recipe agent.
    """
    __tablename__ = "product_catalog"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True, unique=True)
    description = Column(String)
    category = Column(String, nullable=True, index=True)
    image_url = Column(String)
    # 384-dim sentence embedding stored as plain FLOAT[] — no pgvector needed.
    # Populated by embed_products.py. NULL until that script has been run.
    name_embedding = Column(ARRAY(Float), nullable=True)

    inventory_items = relationship("SellerInventory", back_populates="product_catalog", cascade="all, delete")


class SellerInventory(Base):
    """
    Seller-specific inventory row for a given catalog product, in a given shop.
    """
    __tablename__ = "seller_inventory"

    id = Column(Integer, primary_key=True, index=True)
    product_catalog_id = Column(Integer, ForeignKey("product_catalog.id"), nullable=False, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    price = Column(Float, nullable=False)
    stock_quantity = Column(Integer, default=0, nullable=False)

    product_catalog = relationship("ProductCatalog", back_populates="inventory_items")
    shop = relationship("Shop", back_populates="inventory_items")

    __table_args__ = (
        # Composite index covering the exact join pattern used in /api/products/search.
        # Also covers stock_quantity for the WHERE stock_quantity > 0 filter.
        Index("ix_seller_inventory_shop_catalog", "shop_id", "product_catalog_id"),
        Index("ix_seller_inventory_stock", "stock_quantity"),
    )
