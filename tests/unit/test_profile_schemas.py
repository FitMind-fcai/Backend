"""
Unit tests for ProfileBase, ProfileUpdate Pydantic schemas and profile enums.
Pure validation — no database, no HTTP.
"""
import pytest
from pydantic import ValidationError

from app.profile_module.schemas.profile import ProfileBase, ProfileUpdate
from app.profile_module.models.enums import Gender, ActivityLevel, FitnessGoal


VALID = {
    "user_id": 1,
    "age": 28,
    "gender": "Male",
    "height": 178.0,
    "weight": 75.0,
    "fitness_goal": "Lose Weight",
    "activity_level": "Moderately Active",
    "dietary_preference": "None",
    "medical_conditions": "None",
    "allergies": "None",
    "injuries": "None",
    "medications": "None",
}


class TestProfileBaseValidation:
    def test_valid_profile_parses_without_error(self):
        p = ProfileBase(**VALID)
        assert p.age == 28
        assert p.gender == Gender.MALE
        assert p.fitness_goal == FitnessGoal.LOSE_WEIGHT
        assert p.activity_level == ActivityLevel.MODERATELY_ACTIVE

    def test_invalid_gender_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ProfileBase(**{**VALID, "gender": "Unknown"})

    def test_invalid_activity_level_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ProfileBase(**{**VALID, "activity_level": "Super Active"})

    def test_invalid_fitness_goal_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ProfileBase(**{**VALID, "fitness_goal": "Become Immortal"})

    def test_all_valid_genders_accepted(self):
        for g in ("Male", "Female"):
            ProfileBase(**{**VALID, "gender": g})

    def test_all_valid_activity_levels_accepted(self):
        levels = ("Sedentary", "Lightly Active", "Moderately Active", "Very Active", "Extra Active")
        for level in levels:
            ProfileBase(**{**VALID, "activity_level": level})

    def test_all_valid_fitness_goals_accepted(self):
        goals = ("Lose Weight", "Try AI Coach", "Get Bulks", "Improve Endurance")
        for goal in goals:
            ProfileBase(**{**VALID, "fitness_goal": goal})


class TestProfileUpdateValidation:
    def test_empty_update_is_valid_with_user_id_only(self):
        u = ProfileUpdate(user_id=1)
        assert u.age is None
        assert u.gender is None
        assert u.fitness_goal is None

    def test_partial_update_sets_only_provided_fields(self):
        u = ProfileUpdate(user_id=1, age=32, weight=70.5)
        assert u.age == 32
        assert u.weight == 70.5
        assert u.gender is None

    def test_invalid_gender_in_update_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ProfileUpdate(user_id=1, gender="Other")
