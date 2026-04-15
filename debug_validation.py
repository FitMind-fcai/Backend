import json
from app.ai_services.ai_coach.dtos import NutritionPlanDTO

data = {
  "plan_name": "Test",
  "description": "Test",
  "daily_calories": 2000,
  "daily_protein_g": 150,
  "daily_carbs_g": 200,
  "daily_fats_g": 60,
  "days": [
    {
      "day_name": "Monday",
      "day_number": 1,
      "meals": [
        {
          "meal_type": "Breakfast",
          "meal_name": "Oatmeal",
          "calories": 400,
          "protein_g": 20,
          "carbs_g": 50,
          "fats_g": 10,
          "ingredients": [
            {
              "central_food_id": 123,
              "amount_g": 50.0
            }
          ],
          "instructions": "Mix and eat."
        }
      ]
    }
  ]
}

try:
    dto = NutritionPlanDTO.model_validate(data)
    print("Validation passed!")
except Exception as e:
    import traceback
    traceback.print_exc()
