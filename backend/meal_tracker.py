import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

try:
    import neon_http_db
except ImportError:
    from backend import neon_http_db

load_dotenv(Path(__file__).resolve().parent / ".env")


class MealCreate(BaseModel):
    food_name: str = Field(..., min_length=1, max_length=120)
    meal_type: str = Field(..., pattern="^(breakfast|lunch|dinner|snack)$")
    meal_date: date = Field(default_factory=date.today)
    serving: Optional[str] = None
    calories: Optional[float] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    confidence: Optional[float] = None


class MealResponse(MealCreate):
    id: int
    user_id: str
    created_at: datetime

    class Config:
        from_attributes = True


def init_db():
    print("Initializing Neon Postgres database tables...")
    neon_http_db.init_db()


def create_meal(meal_data, user_id: str):
    return neon_http_db.create_meal_record(meal_data, user_id)


def list_meals(user_id: str, meal_date: Optional[date] = None):
    return neon_http_db.list_meals_for_user(user_id, meal_date)


def delete_meal(meal_id: int, user_id: str):
    return neon_http_db.delete_meal_for_user(meal_id, user_id)


def meal_summary(user_id: str, meal_date: Optional[date] = None):
    return neon_http_db.meal_summary_for_user(user_id, meal_date)
