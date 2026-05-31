"""
graph.py — Neo4j Graph Layer for SmartMarket Recommendations
=============================================================

Responsibilities
----------------
1. Driver lifecycle  — initialise the async Neo4j driver once at startup,
                       close it cleanly at shutdown.

2. Graph sync utils  — keep the Neo4j graph in sync with the SQL catalog:
     • sync_product_to_graph()        — upsert a :Product node
     • sync_category_to_graph()       — upsert a :Category node + HAS_CATEGORY edge
     • create_purchase_relationship() — increment BOUGHT_WITH edge weight on checkout

3. Recommendation queries — two Cypher queries per product:
     • get_alternatives()             — SIMILAR_TO edges (same category, different brand)
     • get_bought_together()          — BOUGHT_WITH edges ordered by weight DESC

Architecture notes
------------------
- The official neo4j Python driver 5.x ships an AsyncGraphDatabase that
  integrates cleanly with FastAPI's async event loop.
- All Cypher writes use MERGE so every function is idempotent — safe to
  call multiple times without creating duplicate nodes or edges.
- Product IDs stored in Neo4j are the PostgreSQL ProductCatalog.id integers,
  so the recommendation endpoint can JOIN back to SQL in one query.
- If Neo4j is unavailable (URI not set, connection refused) every function
  degrades gracefully and logs a warning rather than crashing the server.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase, AsyncDriver

load_dotenv()

# ---------------------------------------------------------------------------
# Driver singleton
# ---------------------------------------------------------------------------

_driver: AsyncDriver | None = None

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


async def init_driver() -> None:
    """
    Called once at FastAPI startup.
    Creates the async driver and verifies connectivity.
    Sets _driver to None on failure so all callers degrade gracefully.
    """
    global _driver
    if not NEO4J_PASSWORD:
        print("[graph] NEO4J_PASSWORD not set — graph features disabled.")
        return
    try:
        _driver = AsyncGraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
        )
        await _driver.verify_connectivity()
        print(f"[graph] Connected to Neo4j at {NEO4J_URI}")
        await _ensure_constraints()
    except Exception as exc:
        print(f"[graph] Neo4j connection failed ({exc!r}) — graph features disabled.")
        _driver = None


async def close_driver() -> None:
    """Called once at FastAPI shutdown."""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
        print("[graph] Neo4j driver closed.")


def get_driver() -> AsyncDriver | None:
    return _driver


# ---------------------------------------------------------------------------
# Schema constraints — run once on startup
# ---------------------------------------------------------------------------

async def _ensure_constraints() -> None:
    """
    Create uniqueness constraints so MERGE operations are O(1) index lookups
    rather than full graph scans.
    """
    if not _driver:
        return
    async with _driver.session() as session:
        await session.run(
            "CREATE CONSTRAINT product_id_unique IF NOT EXISTS "
            "FOR (p:Product) REQUIRE p.id IS UNIQUE"
        )
        await session.run(
            "CREATE CONSTRAINT category_name_unique IF NOT EXISTS "
            "FOR (c:Category) REQUIRE c.name IS UNIQUE"
        )
    print("[graph] Neo4j constraints verified.")


# ---------------------------------------------------------------------------
# Graph sync utilities
# ---------------------------------------------------------------------------

async def sync_product_to_graph(
    product_id: int,
    name:       str,
    category:   str | None,
) -> None:
    """
    Upsert a :Product node and optionally link it to a :Category node.

    Cypher pattern:
        MERGE (p:Product {id: $id})
        SET p.name = $name
        MERGE (c:Category {name: $category})
        MERGE (p)-[:HAS_CATEGORY]->(c)

    Safe to call on every product upsert — MERGE is idempotent.
    Also builds SIMILAR_TO edges between products in the same category
    so the alternatives query works immediately after sync.
    """
    if not _driver:
        return
    try:
        async with _driver.session() as session:
            # Upsert the Product node with category as a property
            await session.run(
                """
                MERGE (p:Product {id: $id})
                SET p.name     = $name,
                    p.category = $category
                """,
                id=product_id, name=name, category=category or "Uncategorised",
            )

        print(f"[graph] Synced product id={product_id} '{name}' category='{category}'")

    except Exception as exc:
        # Never crash the main request — graph sync is best-effort
        print(f"[graph] sync_product_to_graph failed for id={product_id}: {exc!r}")


async def create_purchase_relationship(
    catalog_id_a: int,
    catalog_id_b: int,
) -> None:
    """
    Increment the weight on a BOUGHT_WITH edge between two products.
    Called for every pair of distinct items in a successful checkout.

    Cypher pattern:
        MERGE (a)-[r:BOUGHT_WITH]->(b)
        ON CREATE SET r.weight = 1
        ON MATCH  SET r.weight = r.weight + 1

    The edge is bidirectional — we create both directions so the
    recommendation query works regardless of which product is the anchor.
    """
    if not _driver or catalog_id_a == catalog_id_b:
        return
    try:
        async with _driver.session() as session:
            await session.run(
                """
                MATCH (a:Product {id: $id_a}), (b:Product {id: $id_b})
                MERGE (a)-[r:BOUGHT_WITH]->(b)
                ON CREATE SET r.weight = 1
                ON MATCH  SET r.weight = r.weight + 1
                MERGE (b)-[s:BOUGHT_WITH]->(a)
                ON CREATE SET s.weight = 1
                ON MATCH  SET s.weight = s.weight + 1
                """,
                id_a=catalog_id_a, id_b=catalog_id_b,
            )
        print(f"[graph] BOUGHT_WITH incremented: {catalog_id_a} ↔ {catalog_id_b}")
    except Exception as exc:
        print(f"[graph] create_purchase_relationship failed: {exc!r}")


# ---------------------------------------------------------------------------
# Recommendation queries
# ---------------------------------------------------------------------------

async def get_alternatives(product_catalog_id: int) -> list[int]:
    """
    Query 1 — Alternative products in the same category.

    Uses category property matching instead of pre-computed SIMILAR_TO edges,
    which avoids the O(N²) edge explosion on large catalogs.

    Cypher:
        MATCH (p:Product {id: $id})
        MATCH (alt:Product {category: p.category})
        WHERE alt.id <> $id
        RETURN alt.id AS id
        LIMIT 6

    Returns a list of ProductCatalog IDs to hydrate from PostgreSQL.
    """
    if not _driver:
        return []
    try:
        async with _driver.session() as session:
            result = await session.run(
                """
                MATCH (p:Product {id: $id})
                MATCH (alt:Product {category: p.category})
                WHERE alt.id <> $id
                RETURN alt.id AS id
                LIMIT 6
                """,
                id=product_catalog_id,
            )
            records = await result.data()
            return [r["id"] for r in records]
    except Exception as exc:
        print(f"[graph] get_alternatives failed for id={product_catalog_id}: {exc!r}")
        return []


async def get_bought_together(product_catalog_id: int) -> list[int]:
    """
    Query 2 — Frequently bought together.

    Cypher:
        MATCH (p:Product {id: $id})-[r:BOUGHT_WITH]->(together:Product)
        RETURN together.id AS id
        ORDER BY r.weight DESC
        LIMIT 4

    Returns a list of ProductCatalog IDs ordered by co-purchase frequency.
    Returns [] if Neo4j is unavailable or no purchase data exists yet.
    """
    if not _driver:
        return []
    try:
        async with _driver.session() as session:
            result = await session.run(
                """
                MATCH (p:Product {id: $id})-[r:BOUGHT_WITH]->(together:Product)
                RETURN together.id AS id
                ORDER BY r.weight DESC
                LIMIT 4
                """,
                id=product_catalog_id,
            )
            records = await result.data()
            return [r["id"] for r in records]
    except Exception as exc:
        print(f"[graph] get_bought_together failed for id={product_catalog_id}: {exc!r}")
        return []


# ---------------------------------------------------------------------------
# Bulk sync helper — call once after seeding the SQL catalog
# ---------------------------------------------------------------------------

async def bulk_sync_catalog(products: list[dict[str, Any]]) -> None:
    """
    Sync a list of {id, name, category} dicts to Neo4j in one pass.
    Used by the startup event and the seed_graph.py script.

    products: [{"id": 1, "name": "Honey", "category": "Health"}, ...]
    """
    if not _driver:
        print("[graph] bulk_sync_catalog skipped — driver not available.")
        return

    print(f"[graph] Bulk syncing {len(products)} products to Neo4j...")

    # Run syncs concurrently in batches of 50 to avoid overwhelming Neo4j
    BATCH = 50
    for i in range(0, len(products), BATCH):
        batch = products[i: i + BATCH]
        await asyncio.gather(*[
            sync_product_to_graph(p["id"], p["name"], p.get("category"))
            for p in batch
        ])
        print(f"[graph] Synced {min(i + BATCH, len(products))}/{len(products)}")

    print("[graph] Bulk sync complete.")
