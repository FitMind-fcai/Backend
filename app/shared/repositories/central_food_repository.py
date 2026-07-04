from sqlalchemy.orm import Session # type: ignore
from sqlalchemy import func as sql_func, text # type: ignore
from typing import Dict, List, Optional, Tuple
from app.shared.repositories.base_repository import BaseRepository
from app.planning_module.models import CentralFood

# Iconic cuisine staples guaranteed to be offered (via exact keyword match)
# alongside the vector search below. Dense embedding similarity between a
# generic category query (e.g. "Egyptian grains rice bread pasta carbs") and
# a specific dish's bare name (e.g. "Baladi Bread") is inherently weak — the
# query shares category vocabulary with generic USDA rows, not with proper
# noun dish names — so well-known staples can lose the similarity race even
# when they're exactly what the cuisine calls for. This keyword layer mirrors
# the dense+BM25 hybrid retrieval already used for the knowledge-base RAG in
# vector_db_service.py, applied here to the food catalog.
_CUISINE_STAPLE_KEYWORDS: Dict[str, List[str]] = {
    "egyptian": [
        "baladi bread", "ful medames", "foul medames", "koshari", "molokhia",
        "ta'ameya", "taameya", "falafel", "fattah", "hawawshi", "mahshi",
        "shakshuka", "feteer", "basbousa", "kunafa",
    ],
}


def _get_cuisine_staple_keywords(cuisine_label: str) -> List[str]:
    cuisine_lower = cuisine_label.lower()
    if any(k in cuisine_lower for k in ("egypt", "arab", "middle east")):
        return _CUISINE_STAPLE_KEYWORDS["egyptian"]
    return []


class CentralFoodRepository(BaseRepository[CentralFood]):
    """Repository for the central food catalog (USDA foods + manual entries)"""

    def __init__(self, db: Session):
        super().__init__(CentralFood, db)

    def get_by_name(self, name: str) -> Optional[CentralFood]:
        """Exact name lookup (case-insensitive)"""
        return (
            self.db.query(CentralFood)
            .filter(sql_func.lower(CentralFood.food_name) == name.lower())
            .filter(CentralFood.is_active == True)
            .first()
        )

    def get_by_usda_id(self, fdc_id: int) -> Optional[CentralFood]:
        """Lookup by USDA FDC ID"""
        return (
            self.db.query(CentralFood)
            .filter(CentralFood.usda_fdc_id == fdc_id)
            .first()
        )

    def search(
        self,
        query: str,
        food_category: Optional[str] = None,
        limit: int = 30
    ) -> List[CentralFood]:
        """Full-text search by food name — used for food logging search (MyFitnessPal-style)"""
        q = (
            self.db.query(CentralFood)
            .filter(CentralFood.is_active == True)
            .filter(CentralFood.food_name.ilike(f"%{query}%"))
        )
        if food_category:
            q = q.filter(CentralFood.food_category.ilike(f"%{food_category}%"))
        return q.order_by(CentralFood.food_name).limit(limit).all()

    def create_manual_food(self, user_id: int, food_data: dict) -> CentralFood:
        """Create a user-scoped manual food in central_foods with governance flags."""
        payload = dict(food_data)
        payload.update(
            {
                "created_by_user_id": user_id,
                "is_verified": False,
                "is_public": False,
                "source": "ManualUser",
                "is_active": True,
            }
        )
        return self.create(payload)

    def get_by_filters(
        self,
        food_category: Optional[str] = None,
        max_calories_per_100g: Optional[float] = None,
        min_protein_per_100g: Optional[float] = None,
        limit: int = 30
    ) -> List[CentralFood]:
        """Filtered fetch — used to provide AI with food context during plan generation"""
        q = self.db.query(CentralFood).filter(CentralFood.is_active == True)
        if food_category:
            q = q.filter(CentralFood.food_category.ilike(f"%{food_category}%"))
        if max_calories_per_100g:
            q = q.filter(CentralFood.calories_per_100g <= max_calories_per_100g)
        if min_protein_per_100g:
            q = q.filter(CentralFood.protein_per_100g >= min_protein_per_100g)
        return q.limit(limit).all()

    def get_diet_friendly_foods_for_ai(
        self,
        diet_type: str = "balanced",
        allergies: str = "",
        exclude_ingredients: List[str] = None,
        limit: int = 100,
        goal: str = "maintain",
        target_calories: Optional[int] = None,
        target_protein_g: Optional[int] = None,
        cuisine: str = "",
    ) -> Tuple[str, Dict[int, str]]:
        """
        Build a cuisine-aware food pool using pgvector semantic search.

        Searches for foods matching cuisine-specific queries across 4 categories
        (proteins, grains, vegetables, fats), then filters out allergens and
        inappropriate items.

        Returns (prompt_str, food_id_to_name) — the formatted text constraint
        for the LLM, plus an id->name lookup for the foods actually offered.
        The lookup is needed downstream: the LLM only echoes back
        central_food_id numbers in its output, so anything that needs to check
        the ACTUAL food (allergy safety net, meal/ingredient consistency check)
        needs this map to resolve those IDs back to real names.
        """
        from app.ai_services.embedding_utils import embed_text, vec_to_pg_str

        cuisine_val = (cuisine.value if hasattr(cuisine, "value") else str(cuisine or "")).strip()
        cuisine_label = cuisine_val or "healthy"
        goal_norm = (goal or "maintain").lower().replace(" ", "_")

        # Build search queries per food category
        search_queries = [
            (f"{cuisine_label} protein foods meat fish chicken eggs legumes", int(limit * 0.30)),
            (f"{cuisine_label} grains rice bread pasta carbs", int(limit * 0.25)),
            (f"{cuisine_label} vegetables fruits salad greens", int(limit * 0.25)),
            (f"{cuisine_label} healthy fats nuts seeds oil avocado", int(limit * 0.20)),
        ]

        # Build allergy/exclusion filter for SQL
        exclusion_clauses = []
        exclusion_params = {}
        if allergies and allergies.lower() not in ("none", "n/a", "na", "", "nothing"):
            for i, a in enumerate(a.strip() for a in allergies.split(",") if a.strip()):
                key = f"allergy_{i}"
                exclusion_clauses.append(f"food_name NOT ILIKE :{key}")
                exclusion_params[key] = f"%{a}%"
        if exclude_ingredients:
            for i, ex in enumerate(ex.strip() for ex in exclude_ingredients if ex.strip()):
                key = f"excl_{i}"
                exclusion_clauses.append(f"food_name NOT ILIKE :{key}")
                exclusion_params[key] = f"%{ex}%"

        where_extra = (" AND " + " AND ".join(exclusion_clauses)) if exclusion_clauses else ""

        # Diet type macro filter
        diet_filter = ""
        diet_type_lower = str(diet_type).lower()
        if diet_type_lower in ("keto", "low-carb"):
            diet_filter = " AND carbs_per_100g < 10.0"
        elif diet_type_lower == "high-protein":
            diet_filter = " AND protein_per_100g > 15.0"
        elif diet_type_lower == "low-fat":
            diet_filter = " AND fats_per_100g < 5.0"

        seen_ids: set = set()
        all_foods: list = []

        for query_text, per_category_limit in search_queries:
            vec = embed_text(query_text)
            vec_str = vec_to_pg_str(vec)

            # Fetch more than needed so we have room after dedup
            fetch_limit = per_category_limit * 3

            rows = self.db.execute(
                text(f"""
                    SELECT id, food_name, food_name_ar, food_category,
                           calories_per_100g, protein_per_100g, carbs_per_100g,
                           fats_per_100g, fiber_per_100g,
                           1 - (name_embedding <=> CAST(:vec AS vector)) AS similarity
                    FROM central_foods
                    WHERE is_active = true
                      AND name_embedding IS NOT NULL
                      AND calories_per_100g BETWEEN 20 AND 650
                      {diet_filter}
                      {where_extra}
                    ORDER BY name_embedding <=> CAST(:vec AS vector)
                    LIMIT :lim
                """),
                {"vec": vec_str, "lim": fetch_limit, **exclusion_params},
            ).fetchall()

            count = 0
            for r in rows:
                if r.id in seen_ids:
                    continue
                # Deduplicate by food family (max 3 per family)
                family = (r.food_name or "").split("(")[0].split(",")[0].strip().lower()
                family_count = sum(1 for f in all_foods
                                   if (f["food_name"] or "").split("(")[0].split(",")[0].strip().lower() == family)
                if family_count >= 3:
                    continue

                seen_ids.add(r.id)
                all_foods.append(dict(r._mapping))
                count += 1
                if count >= per_category_limit:
                    break

        # Guarantee well-known cuisine staples are offered even if vector
        # search missed them (see _CUISINE_STAPLE_KEYWORDS comment above).
        staple_keywords = _get_cuisine_staple_keywords(cuisine_label)
        if staple_keywords:
            keyword_clauses = " OR ".join(
                f"food_name ILIKE :staple_{i}" for i in range(len(staple_keywords))
            )
            staple_params = {f"staple_{i}": f"%{kw}%" for i, kw in enumerate(staple_keywords)}

            staple_rows = self.db.execute(
                text(f"""
                    SELECT id, food_name, food_name_ar, food_category,
                           calories_per_100g, protein_per_100g, carbs_per_100g,
                           fats_per_100g, fiber_per_100g
                    FROM central_foods
                    WHERE is_active = true
                      AND calories_per_100g BETWEEN 20 AND 650
                      {diet_filter}
                      {where_extra}
                      AND ({keyword_clauses})
                    LIMIT 20
                """),
                {**staple_params, **exclusion_params},
            ).fetchall()

            for r in staple_rows:
                if r.id in seen_ids:
                    continue
                family = (r.food_name or "").split("(")[0].split(",")[0].strip().lower()
                family_count = sum(
                    1 for f in all_foods
                    if (f["food_name"] or "").split("(")[0].split(",")[0].strip().lower() == family
                )
                if family_count >= 3:
                    continue
                seen_ids.add(r.id)
                all_foods.append(dict(r._mapping))

        if not all_foods:
            return (
                "Note: No foods matched the cuisine and dietary filters. Generate generic healthy meals.",
                {},
            )

        prompt_str = f"=== MANDATORY FOOD DATABASE ({len(all_foods)} ITEMS) ===\n"
        prompt_str += "You MUST ONLY generate meals using the exact foods and IDs from this list below. Do not invent new foods.\n"
        prompt_str += "Select foods creatively to form balanced meals.\n\n"

        for f in all_foods:
            prompt_str += (
                f"- [ID: {f['id']}] {f['food_name']} "
                f"(Per 100g: {f['calories_per_100g']} kcal | P:{f['protein_per_100g']}g | C:{f['carbs_per_100g']}g | F:{f['fats_per_100g']}g)\n"
            )

        food_id_to_name = {f["id"]: f["food_name"] for f in all_foods}
        return prompt_str, food_id_to_name

    def search_by_vector(
        self,
        embedding: List[float],
        limit: int = 5,
    ) -> List[dict]:
        """
        Cosine similarity search using pgvector.

        Returns up to *limit* central_foods ordered by closeness to *embedding*.
        Each result is a plain dict with all food fields plus a `similarity_score`.
        Foods with no stored embedding are excluded.
        """
        vec_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"
        rows = self.db.execute(
            text("""
                SELECT
                    id,
                    food_name,
                    food_category,
                    calories_per_100g,
                    protein_per_100g,
                    carbs_per_100g,
                    fats_per_100g,
                    fiber_per_100g,
                    serving_size_g,
                    serving_description,
                    1 - (name_embedding <=> CAST(:vec AS vector)) AS similarity_score
                FROM central_foods
                WHERE is_active = true
                  AND name_embedding IS NOT NULL
                ORDER BY name_embedding <=> CAST(:vec AS vector)
                LIMIT :limit
            """),
            {"vec": vec_str, "limit": limit},
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def set_embedding(self, food_id: int, embedding: List[float]) -> None:
        """Persist the *embedding* vector for a single central_food row."""
        vec_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"
        self.db.execute(
            text("UPDATE central_foods SET name_embedding = CAST(:vec AS vector) WHERE id = :id"),
            {"vec": vec_str, "id": food_id},
        )
        self.db.commit()

    def find_or_create(self, food_data: dict) -> CentralFood:
        """Find by USDA FDC ID first, then by name, or create if not found"""
        if food_data.get("usda_fdc_id"):
            existing = self.get_by_usda_id(food_data["usda_fdc_id"])
            if existing:
                return existing
        existing = self.get_by_name(food_data["food_name"])
        if existing:
            return existing
        food = CentralFood(**food_data)
        self.db.add(food)
        self.db.commit()
        self.db.refresh(food)
        return food
