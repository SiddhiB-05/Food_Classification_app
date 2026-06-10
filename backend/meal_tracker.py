import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sqlalchemy import Date, DateTime, Float, Integer, String, create_engine, func, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


load_dotenv(Path(__file__).resolve().parent / ".env")


DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    # Neon or other cloud Postgres providers might return a URL starting with postgres://,
    # which SQLAlchemy 1.4+ rejects. Also ensure psycopg2 driver is explicitly used.
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+psycopg2://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False) if engine else None


class Base(DeclarativeBase):
    pass


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    food_name: Mapped[str] = mapped_column(String(120), index=True)
    meal_type: Mapped[str] = mapped_column(String(30), index=True)
    meal_date: Mapped[date] = mapped_column(Date, index=True)
    serving: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    calories: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protein_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbs_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    if engine is not None:
        Base.metadata.create_all(bind=engine)
        ensure_user_id_column()


def ensure_user_id_column():
    inspector = inspect(engine)
    if "meals" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("meals")}
    if "user_id" in columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE meals ADD COLUMN user_id VARCHAR(120)"))
        connection.execute(text("UPDATE meals SET user_id = 'demo_user' WHERE user_id IS NULL"))
        connection.execute(text("ALTER TABLE meals ALTER COLUMN user_id SET NOT NULL"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_meals_user_id ON meals (user_id)"))


def get_db_session():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    return SessionLocal()


def create_meal(meal_data, user_id):
    with get_db_session() as db:
        meal = Meal(user_id=user_id, **meal_data.model_dump())
        db.add(meal)
        db.commit()
        db.refresh(meal)
        return meal


def list_meals(user_id, meal_date=None):
    meal_date = meal_date or date.today()
    with get_db_session() as db:
        return (
            db.query(Meal)
            .filter(Meal.user_id == user_id, Meal.meal_date == meal_date)
            .order_by(Meal.created_at.desc())
            .all()
        )


def delete_meal(meal_id, user_id):
    with get_db_session() as db:
        meal = db.query(Meal).filter(Meal.id == meal_id, Meal.user_id == user_id).first()
        if meal is None:
            return False
        db.delete(meal)
        db.commit()
        return True


def meal_summary(user_id, meal_date=None):
    meal_date = meal_date or date.today()
    with get_db_session() as db:
        totals = (
            db.query(
                func.coalesce(func.sum(Meal.calories), 0),
                func.coalesce(func.sum(Meal.protein_g), 0),
                func.coalesce(func.sum(Meal.carbs_g), 0),
                func.coalesce(func.sum(Meal.fat_g), 0),
            )
            .filter(Meal.user_id == user_id, Meal.meal_date == meal_date)
            .one()
        )
        meals_by_type = (
            db.query(Meal.meal_type, func.count(Meal.id))
            .filter(Meal.user_id == user_id, Meal.meal_date == meal_date)
            .group_by(Meal.meal_type)
            .all()
        )

    return {
        "user_id": user_id,
        "date": meal_date.isoformat(),
        "total_calories": round(float(totals[0]), 2),
        "total_protein_g": round(float(totals[1]), 2),
        "total_carbs_g": round(float(totals[2]), 2),
        "total_fat_g": round(float(totals[3]), 2),
        "meals_by_type": {meal_type: count for meal_type, count in meals_by_type},
    }
