import os
import json
import base64
import logging
import threading
from typing import Optional, Dict, Any, List

from openai import OpenAI

from app.ai_services.meal_scanner.dtos import (
    MealScanRequestDTO,
    MealScanResultDTO,
    FoodItemDTO,
    AllergenWarningDTO,
    MatchedFoodDTO,
)

logger = logging.getLogger(__name__)

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "qwen/qwen2.5-vl-72b-instruct"


class MealScannerService:
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_MAX_TOKENS = 2048

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("AI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "AI_API_KEY is not set. "
                "This key is shared by the AI Coach and the Meal Scanner (OpenRouter)."
            )

        self.model = model or os.getenv("QWEN_VL_MODEL", _DEFAULT_MODEL)

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=_OPENROUTER_BASE,
            default_headers={
                "HTTP-Referer": os.getenv(
                    "OPENROUTER_SITE_URL", "http://localhost:8000"
                ),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "FitMind"),
            },
        )
        logger.info("MealScannerService ready — model=%s", self.model)

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_scan_prompt(self, request: MealScanRequestDTO) -> str:
        dietary_ctx = (
            f"\nUser's Dietary Preference: {request.user_dietary_preference}"
            if request.user_dietary_preference
            else ""
        )
        allergen_ctx = (
            f"\nUser's Known Allergies: {request.user_allergies} — flag any item that may contain these!"
            if request.user_allergies
            else ""
        )
        lang_instruction = (
            "\nProvide meal_name and health_notes in Arabic."
            if request.language == "ar"
            else ""
        )

        return f"""Analyze this food image and estimate its nutritional content.
{dietary_ctx}{allergen_ctx}{lang_instruction}

For every visible food item estimate:
1. Portion size (specific: cups / grams / pieces)
2. Calories
3. Protein, carbs, fats (grams)
4. Fiber (if applicable)

Also determine:
- Overall meal name
- Meal type: Breakfast / Lunch / Dinner / Snack
- Allergen warnings (based on user allergies above)
- Health notes (e.g. "High protein", "Good source of fiber")
- Semantic tags: 5-10 short English keywords describing the meal
  (cooking method, main ingredients, cuisine, nutritional profile).
  These tags will be used for vector search — be specific and consistent.
  Example tags: ["grilled", "chicken", "rice", "mediterranean", "high-protein", "low-fat"]

Return ONLY valid JSON — no markdown, no extra text:
{{
    "meal_name": "Descriptive meal name",
    "meal_type": "Breakfast|Lunch|Dinner|Snack",
    "tags": ["tag1", "tag2", "tag3"],
    "food_items": [
        {{
            "name": "Food item name",
            "portion_size": "e.g. 1 cup, 150g",
            "calories": 200,
            "protein_g": 10.0,
            "carbs_g": 25.0,
            "fats_g": 8.0,
            "fiber_g": 3.0,
            "confidence": 0.85
        }}
    ],
    "total_calories": 500,
    "total_protein_g": 25.0,
    "total_carbs_g": 60.0,
    "total_fats_g": 20.0,
    "allergen_warnings": [
        {{
            "allergen": "Allergen name",
            "food_item": "Item containing it",
            "severity": "warning"
        }}
    ],
    "health_notes": "Brief health observation",
    "confidence_score": 0.85
}}

CRITICAL: Return ONLY valid JSON. Be conservative with calorie estimates."""

    # ------------------------------------------------------------------
    # Vision LLM call
    # ------------------------------------------------------------------

    def _call_vision_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        image_format: str = "jpeg",
    ) -> str:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:image/{image_format};base64,{image_b64}"
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            temperature=self.DEFAULT_TEMPERATURE,
            max_tokens=self.DEFAULT_MAX_TOKENS,
        )
        return completion.choices[0].message.content

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(response: str) -> Dict[str, Any]:
        cleaned = response.strip()
        for fence in ("```json", "```"):
            if cleaned.startswith(fence):
                cleaned = cleaned[len(fence) :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return json.loads(cleaned.strip())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_meal(self, request: MealScanRequestDTO, db=None) -> MealScanResultDTO:
        """
        Analyse a meal image and return nutrition + tags + vector-matched foods.

        db: optional SQLAlchemy session for pgvector similarity search.
        """
        logger.info(
            "Scanning meal image — format=%s model=%s user_allergies=%s user_dietary_preference=%s",
            request.image_format,
            self.model,
            request.user_allergies or "none",
            request.user_dietary_preference or "none",
        )

        try:
            system_prompt = (
                "You are an expert nutritionist with deep knowledge of food composition, "
                "regional cuisines, and portion sizes. Analyse food images and return "
                "accurate nutritional estimates as valid JSON only."
            )
            raw = self._call_vision_llm(
                system_prompt=system_prompt,
                user_prompt=self._build_scan_prompt(request),
                image_bytes=request.image_bytes,
                image_format=request.image_format,
            )
            data = self._parse_json(raw)

            food_items = [
                FoodItemDTO(
                    name=item.get("name", "Unknown"),
                    portion_size=item.get("portion_size", "1 serving"),
                    calories=item.get("calories", 0),
                    protein_g=item.get("protein_g", 0.0),
                    carbs_g=item.get("carbs_g", 0.0),
                    fats_g=item.get("fats_g", 0.0),
                    fiber_g=item.get("fiber_g"),
                    confidence=item.get("confidence", 0.5),
                )
                for item in data.get("food_items", [])
            ]
            allergen_warnings = [
                AllergenWarningDTO(
                    allergen=w.get("allergen", "Unknown"),
                    food_item=w.get("food_item", "Unknown"),
                    severity=w.get("severity", "warning"),
                )
                for w in data.get("allergen_warnings", [])
            ]
            tags: List[str] = data.get("tags", [])
            food_item_names: List[str] = [
                item.get("name", "")
                for item in data.get("food_items", [])
                if item.get("name")
            ]

            matched_foods: List[MatchedFoodDTO] = []
            if db is not None and (food_item_names or tags):
                matched_foods = self._find_similar_foods(food_item_names + tags, db)

            meal_name = data.get("meal_name", "Unidentified Meal")
            logger.info(
                "Meal scan OK: %s — %s kcal, tags=%s, matches=%d, allergen_warnings=%s",
                meal_name,
                data.get("total_calories"),
                tags,
                len(matched_foods),
                [w.allergen for w in allergen_warnings] or "none",
            )

            return MealScanResultDTO(
                meal_name=meal_name,
                meal_type=data.get("meal_type", "Snack"),
                food_items=food_items,
                total_calories=data.get("total_calories", 0),
                total_protein_g=data.get("total_protein_g", 0.0),
                total_carbs_g=data.get("total_carbs_g", 0.0),
                total_fats_g=data.get("total_fats_g", 0.0),
                allergen_warnings=allergen_warnings,
                health_notes=data.get("health_notes"),
                confidence_score=data.get("confidence_score", 0.5),
                tags=tags,
                matched_foods=matched_foods,
                scan_successful=True,
            )

        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Qwen2.5-VL response: %s", exc)
            return self._error_result(f"Failed to parse AI response: {exc}")
        except Exception as exc:
            logger.error("Meal scan failed: %s", exc)
            return self._error_result(str(exc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_similar_foods(self, search_terms: List[str], db) -> List[MatchedFoodDTO]:
        """
        Match food names + tags against the catalog using the same shared
        search (CentralFoodRepository.hybrid_search_by_text) used by the
        manual search endpoint and the voice transcriber.
        """
        from app.shared.repositories.central_food_repository import (
            CentralFoodRepository,
        )

        try:
            rows = CentralFoodRepository(db).hybrid_search_by_text(
                search_terms, limit=10
            )
            return [
                MatchedFoodDTO(
                    id=r["id"],
                    food_name=r["food_name"],
                    food_category=r.get("food_category"),
                    calories_per_100g=r.get("calories_per_100g"),
                    protein_per_100g=r.get("protein_per_100g"),
                    carbs_per_100g=r.get("carbs_per_100g"),
                    fats_per_100g=r.get("fats_per_100g"),
                    fiber_per_100g=r.get("fiber_per_100g"),
                    serving_size_g=r.get("serving_size_g"),
                    serving_description=r.get("serving_description"),
                    similarity_score=r["similarity_score"],
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Catalog search failed (returning empty list): %s", exc)
            return []

    @staticmethod
    def _error_result(message: str) -> MealScanResultDTO:
        return MealScanResultDTO(
            meal_name="Scan Failed",
            meal_type="Unknown",
            food_items=[],
            total_calories=0,
            total_protein_g=0.0,
            total_carbs_g=0.0,
            total_fats_g=0.0,
            allergen_warnings=[],
            health_notes=None,
            confidence_score=0.0,
            tags=[],
            matched_foods=[],
            scan_successful=False,
            error_message=message,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_meal_scanner_service: Optional[MealScannerService] = None
_meal_scanner_service_lock = threading.Lock()


def get_meal_scanner_service() -> MealScannerService:
    global _meal_scanner_service
    if _meal_scanner_service is None:
        with _meal_scanner_service_lock:
            if _meal_scanner_service is None:
                _meal_scanner_service = MealScannerService()
    return _meal_scanner_service
