from io import BytesIO
from datetime import date

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

try:
    import meal_tracker
    import auth
    from model_loader import generate_gradcam, open_image_from_bytes, predict_food
    from nutrition_data import get_healthy_alternative, get_nutrition
except ImportError:
    from backend import meal_tracker
    from backend import auth
    from backend.model_loader import generate_gradcam, open_image_from_bytes, predict_food
    from backend.nutrition_data import get_healthy_alternative, get_nutrition


app = FastAPI(
    title="Smart Food Nutrition Analyzer API",
    description="Predicts food from an uploaded image and returns estimated nutrition.",
    version="0.1.0",
)


@app.on_event("startup")
def startup():
    meal_tracker.init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Smart Food Nutrition Analyzer API is running.",
        "predict_endpoint": "POST /predict",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


def _database_error():
    return HTTPException(
        status_code=503,
        detail="Meal tracker database is not configured. Set DATABASE_URL in backend/.env.",
    )


@app.post("/auth/signup", response_model=auth.TokenResponse)
def signup(signup_data: auth.SignupRequest):
    try:
        user = auth.signup_user(signup_data)
        return auth.token_response(user)
    except RuntimeError as exc:
        raise _database_error() from exc


@app.post("/auth/login", response_model=auth.TokenResponse)
def login(login_data: auth.LoginRequest):
    try:
        user = auth.authenticate_user(login_data)
        return auth.token_response(user)
    except RuntimeError as exc:
        raise _database_error() from exc


@app.get("/me", response_model=auth.UserResponse)
def get_me(current_user: auth.User = Depends(auth.get_current_user)):
    return current_user


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a valid image file.",
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        image = open_image_from_bytes(BytesIO(image_bytes))
        prediction = predict_food(image)
        try:
            gradcam_image = generate_gradcam(image)
        except Exception:
            gradcam_image = None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        print("PREDICTION ERROR:", repr(exc))
        raise HTTPException(status_code=500, detail="Prediction failed.") from exc

    food_name = prediction["food"]
    return {
        "filename": file.filename,
        "food": food_name,
        "confidence": prediction["confidence"],
        "scores": prediction["scores"],
        "gradcam_image": gradcam_image,
        "nutrition": get_nutrition(food_name),
        "healthy_alternative": get_healthy_alternative(food_name),
        "note": "Nutrition values are estimates for a standard serving, not exact portion measurement.",
    }


@app.post("/meals", response_model=meal_tracker.MealResponse)
def add_meal(
    meal: meal_tracker.MealCreate,
    current_user: auth.User = Depends(auth.get_current_user),
):
    try:
        return meal_tracker.create_meal(meal, current_user.email)
    except RuntimeError as exc:
        raise _database_error() from exc


@app.get("/meals", response_model=list[meal_tracker.MealResponse])
def get_meals(
    meal_date: date | None = None,
    current_user: auth.User = Depends(auth.get_current_user),
):
    try:
        return meal_tracker.list_meals(current_user.email, meal_date)
    except RuntimeError as exc:
        raise _database_error() from exc


@app.get("/meals/summary")
def get_meal_summary(
    meal_date: date | None = None,
    current_user: auth.User = Depends(auth.get_current_user),
):
    try:
        return meal_tracker.meal_summary(current_user.email, meal_date)
    except RuntimeError as exc:
        raise _database_error() from exc


@app.delete("/meals/{meal_id}")
def remove_meal(
    meal_id: int,
    current_user: auth.User = Depends(auth.get_current_user),
):
    try:
        deleted = meal_tracker.delete_meal(meal_id, current_user.email)
    except RuntimeError as exc:
        raise _database_error() from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Meal not found.")
    return {"deleted": True, "meal_id": meal_id}
