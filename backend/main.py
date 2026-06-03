from io import BytesIO

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

try:
    from model_loader import open_image_from_bytes, predict_food
    from nutrition_data import get_healthy_alternative, get_nutrition
except ImportError:
    from backend.model_loader import open_image_from_bytes, predict_food
    from backend.nutrition_data import get_healthy_alternative, get_nutrition


app = FastAPI(
    title="Smart Food Nutrition Analyzer API",
    description="Predicts food from an uploaded image and returns estimated nutrition.",
    version="0.1.0",
)

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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Prediction failed.") from exc

    food_name = prediction["food"]
    return {
        "filename": file.filename,
        "food": food_name,
        "confidence": prediction["confidence"],
        "scores": prediction["scores"],
        "nutrition": get_nutrition(food_name),
        "healthy_alternative": get_healthy_alternative(food_name),
        "note": "Nutrition values are estimates for a standard serving, not exact portion measurement.",
    }
