"""
seed_graph.py — Neo4j graph population (category-based, no edge explosion)
===========================================================================

Creates Product nodes with category properties.
The recommendation query uses category matching directly in Cypher
instead of pre-computing millions of SIMILAR_TO edges.

Run once after Neo4j is running:
    cd backend
    venv\\Scripts\\activate
    python seed_graph.py
"""

import asyncio
import os

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL   = os.getenv("DATABASE_URL", "")
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

BATCH_SIZE = 500


async def main() -> None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set in .env")
    if not NEO4J_PASSWORD:
        raise RuntimeError("NEO4J_PASSWORD not set in .env")

    engine  = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    await driver.verify_connectivity()
    print("[seed] Connected to Neo4j.")

    # Constraints
    async with driver.session() as s:
        await s.run("CREATE CONSTRAINT product_id_unique IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE")
    print("[seed] Constraints ready.")

    # Load from PostgreSQL
    async with Session() as db:
        result = await db.execute(text("SELECT id, name, category FROM product_catalog ORDER BY id"))
        rows = result.fetchall()
    print(f"[seed] Loaded {len(rows)} products.")

    # Upsert Product nodes in batches using UNWIND (fast bulk write)
    print("[seed] Creating Product nodes...")
    for i in range(0, len(rows), BATCH_SIZE):
        batch = [
            {"id": r[0], "name": r[1], "cat": r[2] or "Uncategorised"}
            for r in rows[i: i + BATCH_SIZE]
        ]
        async with driver.session() as s:
            await s.run(
                """
                UNWIND $batch AS row
                MERGE (p:Product {id: row.id})
                SET p.name = row.name, p.category = row.cat
                """,
                batch=batch
            )
        print(f"[seed] {min(i + BATCH_SIZE, len(rows))}/{len(rows)} nodes upserted")

    # Verify
    async with driver.session() as s:
        r = await s.run("MATCH (p:Product) RETURN count(p) AS n")
        d = await r.data()
        print(f"[seed] Graph contains {d[0]['n']} Product nodes.")
        print("[seed] SIMILAR_TO edges are computed at query time via category matching.")
        print("[seed] BOUGHT_WITH edges are built at runtime as users complete purchases.")

    await driver.close()
    await engine.dispose()
    print("[seed] Done.")


if __name__ == "__main__":
    asyncio.run(main())
