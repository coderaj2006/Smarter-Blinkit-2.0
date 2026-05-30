"""
agent.py — Stage 2: AI Recipe Agent (Semantic Search, no pgvector required)
============================================================================

Execution flow for POST /api/agent/recipe:

  1. Groq LLM Parsing  — intent-aware: handles recipes, health symptoms,
                         cravings, moods. "I have a cold" maps to honey,
                         ginger, tulsi tea, kadha, vitamin C, etc.

  2. In-Python Semantic Search — embeds each search term with
                         all-MiniLM-L6-v2, loads all product embeddings
                         from the DB into a numpy matrix, computes cosine
                         similarity in Python. No pgvector extension needed.

  3. Global DB Scan    — fetches ALL in-stock SellerInventory rows for the
                         top-K semantically similar catalog entries.
                         No LIMIT, no bounding box.

  4. Haversine Sort    — picks the single closest in-stock seller.

  5. ILIKE fallback    — if embeddings haven't been generated yet,
                         falls back to lexical ILIKE so the endpoint
                         always returns something useful.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

import numpy as np
from dotenv import load_dotenv
from groq import Groq
from sentence_transformers import SentenceTransformer
from sqlalchemy import or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models import ProductCatalog, SellerInventory, Shop
from utils import calculate_distance

load_dotenv()

# ---------------------------------------------------------------------------
# Groq client
# ---------------------------------------------------------------------------

_GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
_groq_client   = Groq(api_key=_GROQ_API_KEY) if _GROQ_API_KEY else None
_LLM_AVAILABLE = bool(_GROQ_API_KEY)
_GROQ_MODEL    = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

_SYSTEM_PROMPT = (
    "You are a smart grocery shopping assistant for an Indian supermarket app. "
    "Your job is to interpret ANY user request and return a JSON list of SPECIFIC, "
    "searchable grocery product terms that would directly help the user. "
    "\n\n"
    "CRITICAL RULES:\n"
    "- Respond with ONLY a valid JSON object with a single key 'ingredients'\n"
    "- Each term must be a SPECIFIC product name or type — not a symptom or vague concept\n"
    "- Use the exact words a product label would use (e.g. 'pain relief spray', not 'headache')\n"
    "- For health queries: map symptoms to SPECIFIC remedy products sold in Indian pharmacies/stores\n"
    "- For recipe queries: list specific ingredient names\n"
    "- Do NOT include quantities, units, or brand names\n"
    "- Aim for 5-8 highly specific terms per query\n"
    "\n"
    "HEALTH QUERY MAPPINGS (use these exact product-style terms):\n"
    "headache → ['pain relief spray', 'peppermint essential oil', 'headache relief balm', 'green tea', 'electrolyte drink']\n"
    "cold/cough → ['honey', 'ginger', 'tulsi herbal tea', 'kadha herbal drink', 'vitamin c', 'cough syrup']\n"
    "fever → ['paracetamol tablets', 'tulsi drops', 'neem tablets', 'electrolyte drink', 'herbal kadha']\n"
    "stomach ache → ['antacid tablets', 'ors electrolyte', 'ginger ale', 'probiotic yogurt', 'ajwain']\n"
    "tired/fatigue → ['energy drink', 'protein bar', 'dry fruits', 'multivitamin tablets', 'green tea']\n"
    "sore throat → ['honey', 'ginger tea', 'throat lozenges', 'tulsi drops', 'warm lemon drink']\n"
    "\n"
    "Examples:\n"
    'Input: "I have a headache"\n'
    'Output: {"ingredients": ["pain relief spray", "peppermint essential oil", '
    '"headache relief balm", "green tea relaxing", "electrolyte drink"]}\n'
    "\n"
    'Input: "I have a cold"\n'
    'Output: {"ingredients": ["honey", "ginger", "tulsi herbal tea", '
    '"kadha herbal drink", "vitamin c tablets", "cough syrup ayurvedic"]}\n'
    "\n"
    'Input: "Make pizza for 4"\n'
    'Output: {"ingredients": ["pizza flour", "mozzarella cheese", '
    '"tomato pasta sauce", "olive oil", "yeast", "oregano seasoning"]}\n'
    "\n"
    'Input: "I want something cold to drink"\n'
    'Output: {"ingredients": ["fruit juice chilled", "coconut water", '
    '"iced tea", "cold drink soda", "nimbu pani lemonade"]}'
)

# ---------------------------------------------------------------------------
# Sentence-transformer model — loaded once at module import
# ---------------------------------------------------------------------------

print("[agent] Loading sentence-transformer model (all-MiniLM-L6-v2)...")
_embedder = SentenceTransformer("all-MiniLM-L6-v2")
print("[agent] Embedding model ready.")

# Top-K semantic candidates per ingredient before Haversine sort
_TOP_K = 15

# Minimum cosine similarity score to accept a match.
# Scores below this threshold are rejected even if they're the "best" match,
# preventing irrelevant products (shower gel for headache) from appearing.
# Range: 0.0 (anything) → 1.0 (identical). 0.40 is a good balance.
_MIN_SCORE = 0.40

# In-memory cache: catalog_id → 384-dim unit vector
# Populated on first request, reused for all subsequent ones.
_embedding_cache: dict[int, np.ndarray] = {}
_cache_loaded: bool = False


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------

def _embed(text_input: str) -> np.ndarray:
    """Encode a string to a normalised 384-dim numpy vector."""
    return _embedder.encode(
        text_input,
        normalize_embeddings=True,
        show_progress_bar=False,
    )


# ---------------------------------------------------------------------------
# Embedding cache loader
# ---------------------------------------------------------------------------

async def _load_embedding_cache(db: AsyncSession) -> bool:
    """
    Load all non-NULL product embeddings from the DB into _embedding_cache.
    Returns True if any embeddings were loaded, False otherwise.
    Safe to call multiple times — only runs once per process lifetime.
    """
    global _embedding_cache, _cache_loaded

    if _cache_loaded:
        return len(_embedding_cache) > 0

    try:
        # Check if the column exists
        col_check = await db.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'product_catalog'
              AND column_name = 'name_embedding'
        """))
        if not col_check.fetchone():
            print("[agent] name_embedding column not found — run embed_products.py")
            _cache_loaded = True
            return False

        # Fetch ALL non-NULL embeddings — no LIMIT
        # (LIMIT 2000 was a bug that caused products beyond row 2000 to never appear)
        rows = await db.execute(text("""
            SELECT id, name_embedding::text
            FROM product_catalog
            WHERE name_embedding IS NOT NULL
        """))
        fetched = rows.fetchall()

        if not fetched:
            print("[agent] No embeddings in DB yet — run embed_products.py for semantic search")
            _cache_loaded = True
            return False

        for catalog_id, vec_text in fetched:
            # FLOAT[] comes back as '{0.1,0.2,...}' from Postgres
            nums = [float(x) for x in vec_text.strip("{}").split(",")]
            _embedding_cache[catalog_id] = np.array(nums, dtype=np.float32)

        print(f"[agent] Loaded {len(_embedding_cache)} product embeddings into memory cache.")
        _cache_loaded = True
        return True

    except Exception as exc:
        print(f"[agent] Could not load embedding cache ({exc!r}) — will use ILIKE fallback.")
        _cache_loaded = True
        return False


# ---------------------------------------------------------------------------
# Groq LLM parsing
# ---------------------------------------------------------------------------

async def extract_ingredients(prompt: str) -> list[str]:
    """
    Send the user prompt to Groq and parse the returned JSON ingredient list.
    Falls back to a naive tokeniser if the API key is missing or Groq errors.
    """
    if not _LLM_AVAILABLE or _groq_client is None:
        print("[agent] GROQ_API_KEY not set — using prompt-word fallback.")
        return _fallback_tokenise(prompt)

    try:
        loop = asyncio.get_event_loop()
        completion = await loop.run_in_executor(
            None,
            lambda: _groq_client.chat.completions.create(
                model=_GROQ_MODEL,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.2,
                max_tokens=512,
            ),
        )

        raw_text = completion.choices[0].message.content.strip()
        print(f"[agent] Groq raw response: {raw_text!r}")

        parsed: dict = json.loads(raw_text)

        if isinstance(parsed, list):
            raw_list = parsed
        elif "ingredients" in parsed and isinstance(parsed["ingredients"], list):
            raw_list = parsed["ingredients"]
        else:
            raw_list = next((v for v in parsed.values() if isinstance(v, list)), [])
            if not raw_list:
                raise ValueError(f"No ingredient list in Groq response: {parsed}")

        seen:   set[str]  = set()
        result: list[str] = []
        for item in raw_list:
            clean = str(item).lower().strip()
            if clean and clean not in seen:
                seen.add(clean)
                result.append(clean)

        print(f"[agent] Extracted {len(result)} ingredients: {result}")
        return result

    except Exception as exc:
        print(f"[agent] Groq parsing failed ({exc!r}) — falling back to tokeniser.")
        return _fallback_tokenise(prompt)


def _fallback_tokenise(prompt: str) -> list[str]:
    STOP_WORDS = {
        "make", "for", "me", "a", "an", "the", "i", "want", "need",
        "please", "can", "you", "get", "buy", "order", "some", "of",
        "and", "with", "to", "my", "us", "we", "people", "person",
        "servings", "serving", "portions", "portion", "recipe", "cook",
        "prepare", "dish", "meal", "food", "dinner", "lunch", "breakfast",
        "have", "got", "feeling", "feel",
    }
    tokens = re.split(r"[\s,]+", prompt.lower())
    return [t for t in tokens if len(t) > 2 and t not in STOP_WORDS]


# ---------------------------------------------------------------------------
# Semantic search — in-Python cosine similarity (no pgvector needed)
# ---------------------------------------------------------------------------

async def find_closest_match(
    ingredient: str,
    buyer_lat:  float,
    buyer_lon:  float,
    db:         AsyncSession,
) -> dict[str, Any]:
    """
    Find the single closest in-stock product semantically matching the ingredient.

    1. Ensure embedding cache is loaded from DB.
    2. Embed the ingredient query string.
    3. Batch cosine similarity: stack all cached vectors into a numpy matrix,
       compute dot products in one operation → O(N) but vectorised.
    4. Take top-K catalog IDs by score.
    5. Fetch all in-stock SellerInventory rows for those IDs (no bbox, no limit).
    6. Haversine sort → closest in-stock seller.
    7. ILIKE fallback if no embeddings available.
    """
    has_embeddings = await _load_embedding_cache(db)

    if has_embeddings and _embedding_cache:
        # Embed the query
        loop      = asyncio.get_event_loop()
        query_vec = await loop.run_in_executor(None, lambda: _embed(ingredient))

        # Batch cosine similarity against all cached product vectors
        ids    = list(_embedding_cache.keys())
        matrix = np.stack(list(_embedding_cache.values()))  # (N, 384)
        scores = matrix @ query_vec                          # (N,) cosine similarities

        # Top-K by score — but only keep results above the minimum threshold
        top_k_count = min(_TOP_K, len(ids))
        top_indices = np.argpartition(scores, -top_k_count)[-top_k_count:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        # Filter out low-confidence matches — prevents "shower gel" for "headache"
        top_indices = [i for i in top_indices if scores[i] >= _MIN_SCORE]

        if not top_indices:
            print(f"[agent] '{ingredient}' → all scores below threshold {_MIN_SCORE}, trying ILIKE")
            return await _ilike_fallback(ingredient, buyer_lat, buyer_lon, db)

        catalog_ids = [ids[i] for i in top_indices]
        top_scores  = [float(scores[i]) for i in top_indices]

        print(
            f"[agent] '{ingredient}' → top-{top_k_count} semantic: "
            + ", ".join(f"id={c}({s:.3f})" for c, s in zip(catalog_ids, top_scores))
        )

        # Fetch all in-stock inventory for those catalog IDs — no LIMIT, no bbox
        stmt = (
            select(SellerInventory, ProductCatalog, Shop)
            .join(ProductCatalog, SellerInventory.product_catalog_id == ProductCatalog.id)
            .join(Shop,            SellerInventory.shop_id            == Shop.id)
            .where(
                ProductCatalog.id.in_(catalog_ids),
                SellerInventory.stock_quantity > 0,
            )
        )

        inv_result = await db.execute(stmt)
        rows       = inv_result.all()

        if rows:
            best_row:      tuple | None = None
            best_distance: float        = float("inf")

            for inv, cat, shop in rows:
                dist = calculate_distance(buyer_lat, buyer_lon, shop.latitude, shop.longitude)
                if dist < best_distance:
                    best_distance = dist
                    best_row      = (inv, cat, shop)

            inv, cat, shop = best_row  # type: ignore[misc]
            print(
                f"[agent] '{ingredient}' → semantic match '{cat.name}' "
                f"@ '{shop.shop_name}' ({round(best_distance, 2)} km) "
                f"from {len(rows)} candidate(s)"
            )
            return _build_result(ingredient, inv, cat, shop, best_distance)

        print(f"[agent] '{ingredient}' → semantic candidates all out of stock, trying ILIKE")

    return await _ilike_fallback(ingredient, buyer_lat, buyer_lon, db)


async def _ilike_fallback(
    ingredient: str,
    buyer_lat:  float,
    buyer_lon:  float,
    db:         AsyncSession,
) -> dict[str, Any]:
    """Lexical ILIKE fallback — always works, even without embeddings."""
    pattern = f"%{ingredient}%"

    stmt = (
        select(SellerInventory, ProductCatalog, Shop)
        .join(ProductCatalog, SellerInventory.product_catalog_id == ProductCatalog.id)
        .join(Shop,            SellerInventory.shop_id            == Shop.id)
        .where(
            SellerInventory.stock_quantity > 0,
            or_(
                ProductCatalog.name.ilike(pattern),
                ProductCatalog.description.ilike(pattern),
            ),
        )
    )

    result = await db.execute(stmt)
    rows   = result.all()

    if not rows:
        print(f"[agent] '{ingredient}' → no match anywhere in DB")
        return {
            "ingredient": ingredient,
            "status":     "not_found",
            "message":    f"No in-stock product found for '{ingredient}'",
        }

    best_row:      tuple | None = None
    best_distance: float        = float("inf")

    for inv, cat, shop in rows:
        dist = calculate_distance(buyer_lat, buyer_lon, shop.latitude, shop.longitude)
        if dist < best_distance:
            best_distance = dist
            best_row      = (inv, cat, shop)

    inv, cat, shop = best_row  # type: ignore[misc]
    print(
        f"[agent] '{ingredient}' → ILIKE match '{cat.name}' "
        f"@ '{shop.shop_name}' ({round(best_distance, 2)} km)"
    )
    return _build_result(ingredient, inv, cat, shop, best_distance)


def _build_result(
    ingredient:  str,
    inv:         Any,
    cat:         Any,
    shop:        Any,
    distance_km: float,
) -> dict[str, Any]:
    """Build the standard product result dict — shape matches /api/products/search."""
    return {
        "ingredient":         ingredient,
        "status":             "found",
        "id":                 inv.id,
        "product_catalog_id": cat.id,
        "name":               cat.name,
        "description":        cat.description,
        "category":           cat.category,
        "price":              inv.price,
        "stock_count":        inv.stock_quantity,
        "image_url":          cat.image_url,
        "shop": {
            "id":          shop.id,
            "shop_name":   shop.shop_name,
            "latitude":    shop.latitude,
            "longitude":   shop.longitude,
            "distance_km": round(distance_km, 2),
        },
    }


# ---------------------------------------------------------------------------
# Concurrent resolution of all ingredients
# ---------------------------------------------------------------------------

async def resolve_ingredients_globally(
    ingredients: list[str],
    buyer_lat:   float,
    buyer_lon:   float,
    db:          AsyncSession,
) -> list[dict[str, Any]]:
    """Fire one semantic search per ingredient, all concurrently."""
    tasks = [
        find_closest_match(ingredient, buyer_lat, buyer_lon, db)
        for ingredient in ingredients
    ]
    return await asyncio.gather(*tasks)
