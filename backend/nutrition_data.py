import os

import httpx
from dotenv import load_dotenv


load_dotenv()


NUTRITION_DATA = {
    "burger": {
        "serving": "1 medium burger",
        "calories": 354,
        "protein_g": 17,
        "carbs_g": 29,
        "fat_g": 18,
    },
    "pizza": {
        "serving": "1 slice",
        "calories": 285,
        "protein_g": 12,
        "carbs_g": 36,
        "fat_g": 10,
    },
    "salad": {
        "serving": "1 bowl",
        "calories": 152,
        "protein_g": 5,
        "carbs_g": 11,
        "fat_g": 10,
    },
}

USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
NUTRITIONIX_URL = "https://trackapi.nutritionix.com/v2/natural/nutrients"


HEALTHY_ALTERNATIVES = {
    "burger": "Try a grilled chicken sandwich, paneer wrap, or veggie burger with less sauce.",
    "pizza": "Try thin-crust pizza with extra vegetables or a whole-wheat veggie sandwich.",
    "salad": "Add protein like boiled eggs, paneer, tofu, or grilled chicken for a more balanced meal.",
}


def _fallback_nutrition(food_name):
    return NUTRITION_DATA.get(
        food_name,
        {
            "serving": "standard serving",
            "calories": None,
            "protein_g": None,
            "carbs_g": None,
            "fat_g": None,
        },
    ) | {"source": "local_estimate"}


def _get_nutritionix(food_name):
    app_id = os.getenv("NUTRITIONIX_APP_ID")
    api_key = os.getenv("NUTRITIONIX_API_KEY")
    if not app_id or not api_key:
        return None

    response = httpx.post(
        NUTRITIONIX_URL,
        headers={
            "x-app-id": app_id,
            "x-app-key": api_key,
            "Content-Type": "application/json",
        },
        json={"query": f"1 serving {food_name.replace('_', ' ')}"},
        timeout=8,
    )
    response.raise_for_status()
    foods = response.json().get("foods", [])
    if not foods:
        return None

    food = foods[0]
    return {
        "serving": f"{food.get('serving_qty', 1)} {food.get('serving_unit', 'serving')}",
        "calories": food.get("nf_calories"),
        "protein_g": food.get("nf_protein"),
        "carbs_g": food.get("nf_total_carbohydrate"),
        "fat_g": food.get("nf_total_fat"),
        "source": "nutritionix",
    }


def _nutrient_value(nutrients, nutrient_name):
    for nutrient in nutrients:
        name = nutrient.get("nutrientName", "").lower()
        if nutrient_name in name:
            return nutrient.get("value")
    return None


def _get_usda(food_name):
    api_key = os.getenv("USDA_API_KEY")
    if not api_key:
        return None

    response = httpx.get(
        USDA_SEARCH_URL,
        params={
            "api_key": api_key,
            "query": food_name.replace("_", " "),
            "pageSize": 1,
        },
        timeout=8,
    )
    response.raise_for_status()
    foods = response.json().get("foods", [])
    if not foods:
        return None

    nutrients = foods[0].get("foodNutrients", [])
    return {
        "serving": "100 g",
        "calories": _nutrient_value(nutrients, "energy"),
        "protein_g": _nutrient_value(nutrients, "protein"),
        "carbs_g": _nutrient_value(nutrients, "carbohydrate"),
        "fat_g": _nutrient_value(nutrients, "total lipid"),
        "source": "usda_fooddata_central",
    }


def get_nutrition(food_name):
    for provider in (_get_nutritionix, _get_usda):
        try:
            nutrition = provider(food_name)
        except httpx.HTTPError:
            nutrition = None

        if nutrition:
            return nutrition

    return _fallback_nutrition(food_name)


def get_healthy_alternative(food_name):
    return HEALTHY_ALTERNATIVES.get(food_name, "Choose a balanced portion with protein, fiber, and less added oil.")
