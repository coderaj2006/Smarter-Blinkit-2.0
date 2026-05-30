"""
test_semantic.py — Verify semantic search is working correctly
==============================================================

Run with:
    python test_semantic.py

No server needs to be running — hits the DB directly.
"""

import asyncio
import os
import sys

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

engine        = create_async_engine(DATABASE_URL, echo=False)
AsyncSession_ = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}PASS{RESET}  {msg}")
def fail(msg): print(f"  {RED}FAIL{RESET}  {msg}")
def info(msg): print(f"  {CYAN}INFO{RESET}  {msg}")


async def run_tests():
    from sentence_transformers import SentenceTransformer

    print(f"\n{YELLOW}{'='*60}{RESET}")
    print(f"{YELLOW}  SmartMarket Semantic Search Verification{RESET}")
    print(f"{YELLOW}{'='*60}{RESET}\n")

    async with AsyncSession_() as db:

        # ── Test 1: Check embeddings exist ────────────────────────────────────
        print(f"{CYAN}[Test 1] Checking embeddings in database...{RESET}")
        try:
            r = await db.execute(text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(name_embedding) AS embedded
                FROM product_catalog
            """))
            row = r.fetchone()
            total, embedded = row[0], row[1]

            if embedded == 0:
                fail(f"0/{total} products have embeddings — run embed_products.py first")
                return
            else:
                ok(f"{embedded}/{total} products have embeddings")
        except Exception as e:
            fail(f"Could not query embeddings: {e}")
            return

        # ── Test 2: Load embeddings into memory ───────────────────────────────
        print(f"\n{CYAN}[Test 2] Loading embedding cache...{RESET}")

        r2 = await db.execute(text("""
            SELECT id, name, name_embedding::text
            FROM product_catalog
            WHERE name_embedding IS NOT NULL
        """))
        fetched = r2.fetchall()

        # catalog_id → (product_name, 384-dim vector)
        cache: dict[int, tuple[str, np.ndarray]] = {}
        for catalog_id, prod_name, vec_text in fetched:
            # FLOAT[] comes back as '{0.1,0.2,...}' from Postgres
            nums = [float(x) for x in vec_text.strip("{}").split(",")]
            cache[catalog_id] = (prod_name, np.array(nums, dtype=np.float32))

        ok(f"Loaded {len(cache)} product embeddings into memory")

        # ── Test 3: Semantic similarity queries ───────────────────────────────
        print(f"\n{CYAN}[Test 3] Semantic similarity tests...{RESET}\n")

        model = SentenceTransformer("all-MiniLM-L6-v2")

        test_queries = [
            ("cold drink",         "Should find beverages/juices, NOT just products with 'cold' in name"),
            ("sore throat remedy", "Should find honey, ginger, herbal tea"),
            ("headache relief",    "Should find pain relief, balm, tea"),
            ("energy boost",       "Should find energy drinks, nuts, protein, banana"),
        ]

        ids    = list(cache.keys())
        names  = [cache[i][0] for i in ids]
        matrix = np.stack([cache[i][1] for i in ids])   # (N, 384)

        all_passed = True

        for query, expectation in test_queries:
            query_vec = model.encode(query, normalize_embeddings=True)
            scores    = matrix @ query_vec
            top5_idx  = np.argsort(scores)[::-1][:5]
            top5      = [(names[i], float(scores[i])) for i in top5_idx]

            print(f"  Query: {YELLOW}\"{query}\"{RESET}")
            print(f"  Expect: {expectation}")
            for rank, (name, score) in enumerate(top5, 1):
                bar = "█" * int(score * 20)
                print(f"    {rank}. [{bar:<20}] {score:.3f}  {name}")

            top_score = top5[0][1]
            if top_score > 0.30:
                ok(f"Top match score {top_score:.3f} — semantic search working\n")
            else:
                fail(f"Top match score {top_score:.3f} — suspiciously low\n")
                all_passed = False

        # ── Test 4: Lexical vs Semantic for 'cold' ────────────────────────────
        print(f"{CYAN}[Test 4] Lexical vs Semantic — 'cold drink refreshing beverage'...{RESET}\n")

        query_vec = model.encode("cold drink refreshing beverage", normalize_embeddings=True)
        scores    = matrix @ query_vec
        top10_idx = np.argsort(scores)[::-1][:10]
        top10     = [(names[i], float(scores[i])) for i in top10_idx]

        cold_word_count = sum(1 for name, _ in top10 if "cold" in name.lower())
        other_count     = 10 - cold_word_count

        for rank, (name, score) in enumerate(top10, 1):
            tag = f"{RED}[has 'cold']{RESET}" if "cold" in name.lower() else f"{GREEN}[semantic]{RESET}"
            print(f"    {rank}. {score:.3f}  {name}  {tag}")

        print()
        if other_count >= 5:
            ok(f"{other_count}/10 results are semantic matches — SEMANTIC SEARCH WORKING")
        else:
            fail(f"Only {other_count}/10 semantic matches — may still be lexical")
            all_passed = False

        # ── Summary ───────────────────────────────────────────────────────────
        print(f"\n{YELLOW}{'='*60}{RESET}")
        if all_passed:
            print(f"{GREEN}  All tests passed — semantic search is working{RESET}")
            print(f"{GREEN}  'I have a cold' will recommend honey, ginger, tulsi tea{RESET}")
        else:
            print(f"{RED}  Some tests failed — check output above{RESET}")
        print(f"{YELLOW}{'='*60}{RESET}\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_tests())
