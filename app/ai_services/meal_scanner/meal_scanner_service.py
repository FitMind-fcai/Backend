import os
import json
import logging
from typing import Optional, Dict, Any
from groq import Groq

from app.ai_services.meal_scanner.dtos import (
    MealScanRequestDTO,
    MealScanResultDTO,
    FoodItemDTO,
    AllergenWarningDTO
)

# Configure logger
logger = logging.getLogger(__name__)


class MealScannerService:
    """
    AI-powered meal scanner service using vision models.
    Analyzes food images to estimate nutritional content.
    """
    
    # LLM Configuration - Using Llama 4 Scout for vision capabilities
    DEFAULT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
    DEFAULT_TEMPERATURE = 0.1  # Low temperature for consistent nutrition estimates
    DEFAULT_MAX_TOKENS = 2000
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Initialize the Meal Scanner Service.
        
        Args:
            api_key: Groq API key (falls back to GROQ_API_KEY env variable)
            model: Vision model to use
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Groq API key not provided. Set GROQ_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.model = model or self.DEFAULT_MODEL
        self.client = Groq(api_key=self.api_key)
    
    def _build_scan_prompt(
        self,
        request: MealScanRequestDTO
    ) -> str:
        """Build the prompt for meal scanning."""
        
        dietary_context = ""
        if request.user_dietary_preference:
            dietary_context = f"\nUser's Dietary Preference: {request.user_dietary_preference}"
        
        allergen_context = ""
        if request.user_allergies:
            allergen_context = f"\nUser's Known Allergies: {request.user_allergies} - IMPORTANT: Flag any items that may contain these allergens!"
        
        language_instruction = ""
        if request.language == "ar":
            language_instruction = "\nProvide the meal_name and health_notes in Arabic."
        
        return f"""Analyze this food image and estimate the nutritional content.
{dietary_context}{allergen_context}{language_instruction}

Identify each food item visible in the image and estimate:
1. The portion size (be specific: cups, grams, pieces, etc.)
2. Calories
3. Macronutrients (protein, carbs, fats)
4. Fiber (if applicable)

Also determine:
- Overall meal name (descriptive)
- Meal type (Breakfast, Lunch, Dinner, or Snack)
- Any allergen warnings based on user's allergies
- Health notes (e.g., "High in protein", "Good source of fiber", "High sodium - be mindful")

Return ONLY valid JSON in this exact format:
{{
    "meal_name": "Descriptive meal name",
    "meal_type": "Breakfast/Lunch/Dinner/Snack",
    "food_items": [
        {{
            "name": "Food item name",
            "portion_size": "e.g., 1 cup, 150g",
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
    "health_notes": "Brief health observation about the meal",
    "confidence_score": 0.85
}}

CRITICAL INSTRUCTIONS:
- Return ONLY valid JSON, no additional text or markdown
- Be conservative with estimates - it's better to slightly overestimate calories
- If you cannot identify a food item clearly, give it a lower confidence score
- Always sum up totals from individual items
- Confidence score should reflect how clearly you can see and identify the food"""
    
    def _call_vision_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        image_base64: str,
        image_format: str = "jpeg"
    ) -> str:
        """
        Call the Groq Vision LLM with image.
        
        Args:
            system_prompt: System instruction for the LLM
            user_prompt: User prompt/query
            image_base64: Base64 encoded image
            image_format: Image format (jpeg, png, webp)
            
        Returns:
            LLM response content
        """
        # Construct the image URL for base64 data
        image_url = f"data:image/{image_format};base64,{image_base64}"
        
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        }
                    ]
                }
            ],
            model=self.model,
            temperature=self.DEFAULT_TEMPERATURE,
            max_tokens=self.DEFAULT_MAX_TOKENS
        )
        
        return chat_completion.choices[0].message.content
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse JSON response from LLM, handling potential formatting issues.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Parsed JSON dictionary
        """
        # Clean up response - remove markdown code blocks if present
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        
        return json.loads(cleaned.strip())
    
    def scan_meal(self, request: MealScanRequestDTO) -> MealScanResultDTO:
        """
        Scan a meal image and return nutritional analysis.
        
        Args:
            request: MealScanRequestDTO with image and context
            
        Returns:
            MealScanResultDTO with nutritional analysis
        """
        logger.info(f"📸 Scanning meal image (format: {request.image_format})")
        
        try:
            # Build prompt
            user_prompt = self._build_scan_prompt(request)
            
            system_prompt = """You are an expert nutritionist with extensive knowledge of food composition and portion sizes.
Your task is to analyze food images and provide accurate nutritional estimates.
Always return valid JSON only. Be thorough but conservative in your estimates.
Consider regional cuisines and cooking methods when estimating nutrition."""
            
            # Call vision model
            response = self._call_vision_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_base64=request.image_base64,
                image_format=request.image_format
            )
            
            # Parse response
            scan_data = self._parse_json_response(response)
            
            # Convert to DTOs
            food_items = [
                FoodItemDTO(
                    name=item.get("name", "Unknown"),
                    portion_size=item.get("portion_size", "1 serving"),
                    calories=item.get("calories", 0),
                    protein_g=item.get("protein_g", 0),
                    carbs_g=item.get("carbs_g", 0),
                    fats_g=item.get("fats_g", 0),
                    fiber_g=item.get("fiber_g"),
                    confidence=item.get("confidence", 0.5)
                )
                for item in scan_data.get("food_items", [])
            ]
            
            allergen_warnings = [
                AllergenWarningDTO(
                    allergen=warning.get("allergen", "Unknown"),
                    food_item=warning.get("food_item", "Unknown"),
                    severity=warning.get("severity", "warning")
                )
                for warning in scan_data.get("allergen_warnings", [])
            ]
            
            logger.info(f"✅ Meal scan successful: {scan_data.get('meal_name')} - {scan_data.get('total_calories')} kcal")
            
            return MealScanResultDTO(
                meal_name=scan_data.get("meal_name", "Unidentified Meal"),
                meal_type=scan_data.get("meal_type", "Snack"),
                food_items=food_items,
                total_calories=scan_data.get("total_calories", 0),
                total_protein_g=scan_data.get("total_protein_g", 0),
                total_carbs_g=scan_data.get("total_carbs_g", 0),
                total_fats_g=scan_data.get("total_fats_g", 0),
                allergen_warnings=allergen_warnings,
                health_notes=scan_data.get("health_notes"),
                confidence_score=scan_data.get("confidence_score", 0.5),
                scan_successful=True,
                error_message=None
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse meal scan response: {e}")
            return MealScanResultDTO(
                meal_name="Scan Failed",
                meal_type="Unknown",
                food_items=[],
                total_calories=0,
                total_protein_g=0,
                total_carbs_g=0,
                total_fats_g=0,
                allergen_warnings=[],
                health_notes=None,
                confidence_score=0,
                scan_successful=False,
                error_message=f"Failed to parse AI response: {str(e)}"
            )
        except Exception as e:
            logger.error(f"❌ Meal scan failed: {e}")
            return MealScanResultDTO(
                meal_name="Scan Failed",
                meal_type="Unknown",
                food_items=[],
                total_calories=0,
                total_protein_g=0,
                total_carbs_g=0,
                total_fats_g=0,
                allergen_warnings=[],
                health_notes=None,
                confidence_score=0,
                scan_successful=False,
                error_message=str(e)
            )


# Singleton instance
_meal_scanner_service: Optional[MealScannerService] = None


def get_meal_scanner_service() -> MealScannerService:
    """
    Get the singleton MealScannerService instance.
    
    Returns:
        MealScannerService instance
    """
    global _meal_scanner_service
    if _meal_scanner_service is None:
        _meal_scanner_service = MealScannerService()
    return _meal_scanner_service
