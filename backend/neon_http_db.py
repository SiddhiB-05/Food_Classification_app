import json
import os
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _get_connection_details():
    raw_url = os.getenv("DATABASE_URL", "")
    if not raw_url:
        raise RuntimeError("DATABASE_URL environment variable is not configured.")

    formatted_url = raw_url
    if formatted_url.startswith("postgresql+psycopg2://"):
        formatted_url = formatted_url.replace("postgresql+psycopg2://", "postgresql://", 1)

    if "@" in formatted_url and "." in formatted_url:
        host = formatted_url.split("@")[1].split("/")[0]
        return f"https://{host}/sql", formatted_url
    else:
        raise RuntimeError("Invalid DATABASE_URL format for Neon Postgres.")


def execute_sql(sql: str, params: Optional[list] = None) -> dict:
    http_url, conn_str = _get_connection_details()
    body = {"query": sql}
    if params is not None:
        body["params"] = params

    req = urllib.request.Request(
        http_url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Neon-Connection-String": conn_str,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Neon HTTP Database Error ({exc.code}): {err_msg}") from exc
    except Exception as exc:
        raise RuntimeError(f"Neon HTTP Connection Error: {exc}") from exc


class User:
    def __init__(self, id: int, name: str, email: str, password_hash: str, created_at: any):
        self.id = id
        self.name = name
        self.email = email
        self.password_hash = password_hash
        if isinstance(created_at, datetime):
            self.created_at = created_at
        elif isinstance(created_at, str):
            clean_str = created_at.replace("Z", "+00:00")
            try:
                self.created_at = datetime.fromisoformat(clean_str)
            except ValueError:
                self.created_at = datetime.utcnow()
        else:
            self.created_at = datetime.utcnow()

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"


class Meal:
    def __init__(
        self,
        id: int,
        user_id: str,
        food_name: str,
        meal_type: str,
        meal_date: any,
        serving: Optional[str] = None,
        calories: Optional[float] = None,
        protein_g: Optional[float] = None,
        carbs_g: Optional[float] = None,
        fat_g: Optional[float] = None,
        confidence: Optional[float] = None,
        created_at: any = None,
    ):
        self.id = id
        self.user_id = user_id
        self.food_name = food_name
        self.meal_type = meal_type

        if isinstance(meal_date, date):
            self.meal_date = meal_date
        elif isinstance(meal_date, str):
            try:
                self.meal_date = date.fromisoformat(meal_date[:10])
            except ValueError:
                self.meal_date = date.today()
        else:
            self.meal_date = date.today()

        self.serving = serving
        self.calories = float(calories) if calories is not None else None
        self.protein_g = float(protein_g) if protein_g is not None else None
        self.carbs_g = float(carbs_g) if carbs_g is not None else None
        self.fat_g = float(fat_g) if fat_g is not None else None
        self.confidence = float(confidence) if confidence is not None else None

        if isinstance(created_at, datetime):
            self.created_at = created_at
        elif isinstance(created_at, str):
            clean_str = created_at.replace("Z", "+00:00")
            try:
                self.created_at = datetime.fromisoformat(clean_str)
            except ValueError:
                self.created_at = datetime.utcnow()
        else:
            self.created_at = datetime.utcnow()

    def __repr__(self):
        return f"<Meal id={self.id} food_name={self.food_name}>"


def init_db():
    execute_sql("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(120) NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    execute_sql("ALTER TABLE users ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")

    execute_sql("""
    CREATE TABLE IF NOT EXISTS meals (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(120) NOT NULL,
        food_name VARCHAR(120) NOT NULL,
        meal_type VARCHAR(30) NOT NULL,
        meal_date DATE NOT NULL,
        serving VARCHAR(120),
        calories DOUBLE PRECISION,
        protein_g DOUBLE PRECISION,
        carbs_g DOUBLE PRECISION,
        fat_g DOUBLE PRECISION,
        confidence DOUBLE PRECISION,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    execute_sql("ALTER TABLE meals ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")


def get_user_by_email(email: str) -> Optional[User]:
    res = execute_sql("SELECT id, name, email, password_hash, created_at FROM users WHERE LOWER(email) = LOWER($1) LIMIT 1;", [email])
    rows = res.get("rows", [])
    if not rows:
        return None
    r = rows[0]
    return User(
        id=r["id"],
        name=r["name"],
        email=r["email"],
        password_hash=r["password_hash"],
        created_at=r["created_at"],
    )


def create_user(name: str, email: str, password_hash: str) -> User:
    res = execute_sql(
        "INSERT INTO users (name, email, password_hash) VALUES ($1, $2, $3) RETURNING id, name, email, password_hash, created_at;",
        [name, email.lower(), password_hash],
    )
    rows = res.get("rows", [])
    r = rows[0]
    return User(
        id=r["id"],
        name=r["name"],
        email=r["email"],
        password_hash=r["password_hash"],
        created_at=r["created_at"],
    )


def create_meal_record(meal_data, user_id: str) -> Meal:
    data = meal_data.model_dump() if hasattr(meal_data, "model_dump") else meal_data
    meal_date_val = data["meal_date"].isoformat() if isinstance(data["meal_date"], date) else str(data["meal_date"])

    res = execute_sql(
        """
        INSERT INTO meals (user_id, food_name, meal_type, meal_date, serving, calories, protein_g, carbs_g, fat_g, confidence)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id, user_id, food_name, meal_type, meal_date, serving, calories, protein_g, carbs_g, fat_g, confidence, created_at;
        """,
        [
            user_id.lower(),
            data["food_name"],
            data["meal_type"],
            meal_date_val,
            data.get("serving"),
            data.get("calories"),
            data.get("protein_g"),
            data.get("carbs_g"),
            data.get("fat_g"),
            data.get("confidence"),
        ],
    )
    rows = res.get("rows", [])
    r = rows[0]
    return Meal(**r)


def list_meals_for_user(user_id: str, meal_date_val: Optional[date] = None) -> List[Meal]:
    target_date = meal_date_val or date.today()
    date_str = target_date.isoformat()

    res = execute_sql(
        """
        SELECT id, user_id, food_name, meal_type, meal_date, serving, calories, protein_g, carbs_g, fat_g, confidence, created_at
        FROM meals
        WHERE LOWER(user_id) = LOWER($1) AND meal_date = $2
        ORDER BY created_at DESC;
        """,
        [user_id, date_str],
    )
    return [Meal(**r) for r in res.get("rows", [])]


def delete_meal_for_user(meal_id: int, user_id: str) -> bool:
    res = execute_sql(
        "DELETE FROM meals WHERE id = $1 AND LOWER(user_id) = LOWER($2) RETURNING id;",
        [meal_id, user_id],
    )
    return len(res.get("rows", [])) > 0


def meal_summary_for_user(user_id: str, meal_date_val: Optional[date] = None) -> dict:
    target_date = meal_date_val or date.today()
    date_str = target_date.isoformat()

    res_totals = execute_sql(
        """
        SELECT
            COALESCE(SUM(calories), 0) AS total_calories,
            COALESCE(SUM(protein_g), 0) AS total_protein_g,
            COALESCE(SUM(carbs_g), 0) AS total_carbs_g,
            COALESCE(SUM(fat_g), 0) AS total_fat_g
        FROM meals
        WHERE LOWER(user_id) = LOWER($1) AND meal_date = $2;
        """,
        [user_id, date_str],
    )
    totals_row = res_totals.get("rows", [{}])[0]

    res_types = execute_sql(
        """
        SELECT meal_type, COUNT(id) AS count
        FROM meals
        WHERE LOWER(user_id) = LOWER($1) AND meal_date = $2
        GROUP BY meal_type;
        """,
        [user_id, date_str],
    )

    meals_by_type = {r["meal_type"]: int(r["count"]) for r in res_types.get("rows", [])}

    return {
        "user_id": user_id,
        "date": date_str,
        "total_calories": round(float(totals_row.get("total_calories", 0)), 2),
        "total_protein_g": round(float(totals_row.get("total_protein_g", 0)), 2),
        "total_carbs_g": round(float(totals_row.get("total_carbs_g", 0)), 2),
        "total_fat_g": round(float(totals_row.get("total_fat_g", 0)), 2),
        "meals_by_type": meals_by_type,
    }
