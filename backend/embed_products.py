"""
embed_products.py — One-time semantic embedding generation
===========================================================

Stores 384-dim embeddings as a plain PostgreSQL FLOAT[] column.
No pgvector extension required — works on any PostgreSQL version.

Run once after seeding the product catalog:
    cd backend
    venv\\Scripts\\activate
    python embed_products.py

Re-running is safe — only NULL rows are processed.
"""

import asyncio
import os

import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in .env")

BATCH_SIZE = 256
MODEL_NAME = "all-MiniLM-L6-v2"


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with engine.begin() as conn:
        print("[embed] Ensuring name_embedding column exists (plain FLOAT[])...")
        await conn.execute(text("""
            ALTER TABLE product_catalog
            ADD COLUMN IF NOT EXISTS name_embedding FLOAT[]
        """))
        print("[embed] Column ready.")

    print(f"[embed] Loading model '{MODEL_NAME}'...")
    model = SentenceTransformer(MODEL_NAME)
    print("[embed] Model loaded.")

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            SELECT id, name FROM product_catalog
            WHERE name_embedding IS NULL
            ORDER BY id
        """))
        rows = result.fetchall()

        if not rows:
            print("[embed] All products already have embeddings. Nothing to do.")
            await engine.dispose()
            return

        total = len(rows)
        print(f"[embed] Embedding {total} products in batches of {BATCH_SIZE}...")
        total_updated = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = rows[batch_start: batch_start + BATCH_SIZE]
            ids   = [r[0] for r in batch]
            names = [r[1] for r in batch]

            # Encode — returns (N, 384) float32 numpy array
            vectors: np.ndarray = model.encode(
                names,
                batch_size=BATCH_SIZE,
                show_progress_bar=False,
                normalize_embeddings=True,
            )

            # Write each vector as a real Python list — asyncpg handles
            # list → FLOAT[] natively without any string casting
            for row_id, vec in zip(ids, vectors):
                float_list = [float(v) for v in vec]
                await db.execute(
                    text("""
                        UPDATE product_catalog
                        SET name_embedding = :arr
                        WHERE id = :id
                    """),
                    {"arr": float_list, "id": row_id},
                )

            await db.commit()
            total_updated += len(batch)
            print(
                f"[embed] {total_updated}/{total} done "
                f"(batch {batch_start // BATCH_SIZE + 1})"
            )

    print(f"[embed] Done. {total_updated} embeddings written.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
