from enum import Enum

class PlanType(str, Enum):
    """Type of plan user wants to generate"""
    WORKOUT = "Workout"
    NUTRITION = "Nutrition"

class WorkoutLocation(str, Enum):
    """Where user will perform workouts"""
    GYM = "Gym"
    HOME = "Home"
    OUTDOOR = "Outdoor"
    HYBRID = "Hybrid"  # Mix of locations

class EquipmentAvailability(str, Enum):
    """Equipment access for workouts"""
    FULL_GYM = "Full Gym Equipment"
    BASIC_EQUIPMENT = "Basic Equipment"  # Dumbbells, resistance bands
    NO_EQUIPMENT = "No Equipment"  # Bodyweight only

class WorkoutFocus(str, Enum):
    """Primary focus of workout plan"""
    STRENGTH = "Strength Training"
    CARDIO = "Cardiovascular"
    FLEXIBILITY = "Flexibility"
    HYBRID = "Hybrid"  # Balanced mix
    SPORT_SPECIFIC = "Sport Specific"

class WorkoutDifficulty(str, Enum):
    """Workout intensity level"""
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"

class CaloriePreference(str, Enum):
    """How to set calorie targets"""
    AUTO = "Auto"
    CUSTOM = "Custom"

class MealComplexity(str, Enum):
    """Cooking time and complexity preference"""
    QUICK = "Quick"
    MODERATE = "Moderate"
    ELABORATE = "Elaborate"
    MIXED = "Mixed"

class CuisineType(str, Enum):
    """Preferred cuisine styles"""
    MEDITERRANEAN = "Mediterranean"
    ASIAN = "Asian"
    WESTERN = "Western"
    MIDDLE_EASTERN = "Middle Eastern"
    LATIN = "Latin American"
    VEGETARIAN = "Vegetarian"
    VEGAN = "Vegan"
    MIXED = "Mixed"
