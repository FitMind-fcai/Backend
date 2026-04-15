from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
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
            
        # Get a diverse randomized selection of matching foods
        foods = query.order_by(sql_func.random()).limit(limit).all()
        
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
