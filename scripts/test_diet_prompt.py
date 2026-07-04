import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import SessionLocal
from app.shared.repositories.central_food_repository import CentralFoodRepository

def test_ai_food_payload():
    db = SessionLocal()
    repo = CentralFoodRepository(db)

    # Simulating a user profile and preferences
    print("--- TESTING ALLERGIES & PREFERENCES ---")
    payload, food_id_to_name = repo.get_diet_friendly_foods_for_ai(
        diet_type="high-protein",
        allergies="peanut, milk",
        exclude_ingredients=["egg"],
        limit=5
    )
    print(payload)
    print(food_id_to_name)
    db.close()

if __name__ == "__main__":
    test_ai_food_payload()
