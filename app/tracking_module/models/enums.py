from enum import Enum
import enum


class LogMethod(str, Enum):
    TEXT = "TEXT"
    VOICE = "VOICE"
    CAMERA = "CAMERA"


class MealType(str, enum.Enum):
    BREAKFAST = "Breakfast"
    LUNCH = "Lunch"
    DINNER = "Dinner"
    SNACK = "Snack"
