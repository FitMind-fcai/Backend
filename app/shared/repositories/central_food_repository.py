from sqlalchemy.orm import Session # type: ignore
from sqlalchemy import func as sql_func, text # type: ignore
from typing import List, Optional
from app.shared.repositories.base_repository import BaseRepository
from app.planning_module.models import CentralFood


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

    def search_for_tracking(self, query: str, user_id: int, limit: int = 20) -> List[CentralFood]:
        """Search foods visible to user: verified/public + user's private entries."""
        q = (
            self.db.query(CentralFood)
            .filter(CentralFood.is_active == True)
            .filter(CentralFood.food_name.ilike(f"%{query}%"))
            .filter(
                (CentralFood.is_verified == True)
                | (CentralFood.is_public == True)
                | (CentralFood.created_by_user_id == user_id)
            )
        )
        return q.order_by(CentralFood.food_name.asc()).limit(limit).all()

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
        limit: int = 50
    ) -> str:
        """
        Fetch a diverse list of foods matching a diet type while strictly EXCLUDING allergens,
        unwanted ingredients, and nutritionally inappropriate items (baby food, alcohol, candy,
        fast food, near-zero-calorie fillers). Returns formatted text constraint for the LLM.
        """
        query = self.db.query(CentralFood).filter(CentralFood.is_active == True)
        
        # 1. Macro / Diet Type Constraints
        diet_type = str(diet_type).lower()
        if diet_type in ["keto", "low-carb"]:
            query = query.filter(CentralFood.carbs_per_100g < 10.0)
        elif diet_type == "high-protein":
            query = query.filter(CentralFood.protein_per_100g > 15.0)
        elif diet_type == "low-fat":
            query = query.filter(CentralFood.fats_per_100g < 5.0)
            
        # 2. Exclude Allergies (comma-separated string)
        if allergies and allergies.lower() not in ["none", "n/a", "na", "", "nothing"]:
            allergy_items = [a.strip() for a in allergies.split(",") if a.strip()]
            for allergy in allergy_items:
                query = query.filter(~CentralFood.food_name.ilike(f"%{allergy}%"))
                
        # 3. Exclude Specific Ingredients (List of strings)
        if exclude_ingredients:
            for ex in exclude_ingredients:
                ex = str(ex).strip()
                if ex:
                    query = query.filter(~CentralFood.food_name.ilike(f"%{ex}%"))

        # 4. Exclude obviously inappropriate foods by name keywords
        BAD_NAME_KEYWORDS = [
            "babyfood", "baby food", "toddler", "infant",
            "alcoholic", "wine", "beer", "malt beverage", "spirits", "liqueur", "carignane",
            "candy", "candies", "toblerone", "nougat", "chocolate bar",
            "mcdonald", "burger king", "wendy",
            "corn nut", "cornnuts",
            "ice cream", "milk shake", "milkshake",
            "margarine",
            "gravy",
        ]
        for bad in BAD_NAME_KEYWORDS:
            query = query.filter(~CentralFood.food_name.ilike(f"%{bad}%"))

        # 5. Sensible calorie + protein floor (exclude near-zero-calorie fillers and pure fats)
        query = (
            query
            .filter(CentralFood.calories_per_100g >= 30.0)   # at least 30 kcal / 100 g
            .filter(CentralFood.calories_per_100g <= 650.0)  # skip pure oils / solid fats
            .filter(CentralFood.protein_per_100g >= 1.5)     # at least 1.5 g protein / 100 g
        )
            
        # Deterministic retrieval: avoid random() so core ingredient families are consistently present.
        foods_pool = query.order_by(CentralFood.food_name.asc()).limit(max(limit * 12, 240)).all()
        foods = self._select_balanced_foods_for_prompt(foods_pool, limit)
        
        if not foods:
            return "Note: No strict food constraints applied due to overly restrictive filters. Generate generic healthy meals."

        prompt_str = f"=== MANDATORY FOOD DATABASE ({len(foods)} ITEMS) ===\n"
        prompt_str += "You MUST ONLY generate meals using the exact foods and IDs from this list below. Do not invent new foods.\n"
        prompt_str += "Select foods creatively to form balanced meals.\n\n"
        
        for f in foods:
            prompt_str += (
                f"- [ID: {f.id}] {f.food_name} "
                f"(Per 100g: {f.calories_per_100g} kcal | P:{f.protein_per_100g}g | C:{f.carbs_per_100g}g | F:{f.fats_per_100g}g)\n"
            )
        
        return prompt_str

    def _select_balanced_foods_for_prompt(self, foods: List[CentralFood], limit: int) -> List[CentralFood]:
        """Build a deterministic, balanced food set for AI prompts."""
        if not foods:
            return []

        limit = max(12, int(limit or 50))

        proteins: List[CentralFood] = []
        carbs: List[CentralFood] = []
        produce: List[CentralFood] = []
        fats: List[CentralFood] = []
        others: List[CentralFood] = []

        for food in foods:
            bucket = self._classify_food_bucket(food)
            if bucket == "protein":
                proteins.append(food)
            elif bucket == "carb":
                carbs.append(food)
            elif bucket == "produce":
                produce.append(food)
            elif bucket == "fat":
                fats.append(food)
            else:
                others.append(food)

        quotas = {
            "protein": max(3, int(limit * 0.30)),
            "carb": max(3, int(limit * 0.25)),
            "produce": max(3, int(limit * 0.25)),
            "fat": max(2, int(limit * 0.20)),
        }

        selected: List[CentralFood] = []
        selected_ids = set()

        def _pick(items: List[CentralFood], amount: int, key_name: str) -> None:
            if amount <= 0 or not items:
                return
            ranked = self._rank_bucket_items(items, key_name)
            for candidate in ranked:
                if len(selected) >= limit:
                    break
                if candidate.id in selected_ids:
                    continue
                selected.append(candidate)
                selected_ids.add(candidate.id)
                if len([f for f in selected if self._classify_food_bucket(f) == key_name]) >= amount:
                    break

        _pick(proteins, quotas["protein"], "protein")
        _pick(carbs, quotas["carb"], "carb")
        _pick(produce, quotas["produce"], "produce")
        _pick(fats, quotas["fat"], "fat")

        # Fill any remaining slots with deterministic best-of leftovers.
        leftovers = proteins + carbs + produce + fats + others
        leftovers_ranked = sorted(
            leftovers,
            key=lambda f: (
                -(f.protein_per_100g or 0),
                -(f.fiber_per_100g or 0),
                -(f.carbs_per_100g or 0),
                f.food_name.lower(),
            ),
        )
        for food in leftovers_ranked:
            if len(selected) >= limit:
                break
            if food.id in selected_ids:
                continue
            selected.append(food)
            selected_ids.add(food.id)

        return selected[:limit]

    def _classify_food_bucket(self, food: CentralFood) -> str:
        """Classify food into broad meal-building buckets."""
        name = (food.food_name or "").lower()
        category = (food.food_category or "").lower()

        produce_terms = [
            "vegetable", "fruit", "greens", "salad", "tomato", "cucumber", "pepper",
            "broccoli", "spinach", "lettuce", "apple", "banana", "berry", "orange",
        ]
        protein_terms = [
            "chicken", "turkey", "beef", "fish", "salmon", "tuna", "egg", "tofu",
            "tempeh", "lentil", "bean", "yogurt", "cottage", "protein",
        ]
        carb_terms = [
            "rice", "bread", "oat", "pasta", "potato", "quinoa", "barley", "cereal",
            "tortilla", "wrap", "noodle",
        ]
        fat_terms = [
            "avocado", "olive", "almond", "walnut", "cashew", "peanut", "seed", "nut",
            "tahini", "flax", "chia",
        ]

        search_space = f"{name} {category}"

        if any(term in search_space for term in produce_terms):
            return "produce"
        if any(term in search_space for term in protein_terms) or (food.protein_per_100g or 0) >= 15:
            return "protein"
        if any(term in search_space for term in fat_terms) or ((food.fats_per_100g or 0) >= 12 and (food.protein_per_100g or 0) < 12):
            return "fat"
        if any(term in search_space for term in carb_terms) or (food.carbs_per_100g or 0) >= 20:
            return "carb"
        return "other"

    def _rank_bucket_items(self, items: List[CentralFood], bucket: str) -> List[CentralFood]:
        """Deterministic ranking by bucket-specific nutritional signals."""
        if bucket == "protein":
            return sorted(items, key=lambda f: (-(f.protein_per_100g or 0), f.food_name.lower()))
        if bucket == "carb":
            return sorted(items, key=lambda f: (-(f.carbs_per_100g or 0), -(f.fiber_per_100g or 0), f.food_name.lower()))
        if bucket == "produce":
            return sorted(items, key=lambda f: (-(f.fiber_per_100g or 0), f.food_name.lower()))
        if bucket == "fat":
            return sorted(items, key=lambda f: (-(f.fats_per_100g or 0), f.food_name.lower()))
        return sorted(items, key=lambda f: f.food_name.lower())

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
