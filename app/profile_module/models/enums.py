from enum import Enum

class Gender(str, Enum):
    """User's gender options"""
    MALE = "Male"
    FEMALE = "Female"

class ActivityLevel(str, Enum):
    """User's daily activity level for calorie calculation"""
    SEDENTARY = "Sedentary"  # Little to no exercise
    LIGHTLY_ACTIVE = "Lightly Active"  # Exercise 1-3 days/week
    MODERATELY_ACTIVE = "Moderately Active"  # Exercise 3-5 days/week
    VERY_ACTIVE = "Very Active"  # Exercise 6-7 days/week
    EXTRA_ACTIVE = "Extra Active"  # Very intense exercise daily

class FitnessGoal(str, Enum):
    """User's primary fitness objective"""
    LOSE_WEIGHT = "Lose Weight"  # Weight loss focus
    MAINTAIN_WEIGHT = "Maintain Weight"  # Weight maintenance
    BUILD_MUSCLE = "Build Muscle"  # Muscle gain focus
