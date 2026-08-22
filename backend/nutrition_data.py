import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent / ".env")


USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
OPEN_FOOD_FACTS_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
FATSECRET_TOKEN_URL = "https://oauth.fatsecret.com/connect/token"
FATSECRET_SEARCH_URL = "https://platform.fatsecret.com/rest/foods/search/v2"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.5-flash"
FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
]
MAX_RETRIES = 3
CACHE_FILE = Path(__file__).resolve().parent / ".gemini_cache.json"

_fatsecret_token = None
_fatsecret_token_expires_at = 0
_healthy_alternative_cache = {}
_gemini_cache = None
NUTRIENT_KEYS = ("calories", "protein_g", "carbs_g", "fat_g")


def _unavailable_nutrition():
    return {
        "serving": None,
        "calories": None,
        "protein_g": None,
        "carbs_g": None,
        "fat_g": None,
        "source": "api_unavailable",
    }


def _nutrient_value(nutrients, nutrient_name):
    for nutrient in nutrients:
        name = nutrient.get("nutrientName", "").lower()
        if nutrient_name in name:
            return nutrient.get("value")
    return None


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_any_nutrition_value(nutrition):
    return any(nutrition.get(key) is not None for key in NUTRIENT_KEYS)


def _has_complete_nutrition(nutrition):
    return all(nutrition.get(key) is not None for key in NUTRIENT_KEYS)


def _is_per_100g(nutrition):
    return "100 g" in (nutrition.get("serving") or "").lower()


def _value_count(nutrition):
    return sum(nutrition.get(key) is not None for key in NUTRIENT_KEYS)


def _merge_missing_nutrition(base, extra):
    merged = base.copy()
    used_sources = [base.get("source")]

    for key in NUTRIENT_KEYS:
        if merged.get(key) is None and extra.get(key) is not None:
            merged[key] = extra[key]
            used_sources.append(extra.get("source"))

    sources = []
    for source in used_sources:
        if source and source not in sources:
            sources.append(source)
    merged["source"] = "+".join(sources)
    return merged


def _get_gemini_api_key():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    placeholder_values = {"your_actual_key", "your_gemini_api_key", "replace_me"}
    if api_key.strip().lower() in placeholder_values:
        return None
    return api_key.strip()


def _unique_values(values):
    unique = []
    for value in values:
        value = (value or "").strip()
        if value and value not in unique:
            unique.append(value)
    return unique


def _gemini_models():
    configured_models = os.getenv("GEMINI_FALLBACK_MODELS")
    if configured_models:
        fallback_models = [
            model.strip()
            for model in configured_models.split(",")
            if model.strip()
        ]
    else:
        fallback_models = FALLBACK_MODELS

    return _unique_values([os.getenv("GEMINI_MODEL") or DEFAULT_MODEL, *fallback_models])


def _load_gemini_cache():
    global _gemini_cache

    if _gemini_cache is not None:
        return _gemini_cache

    if not CACHE_FILE.exists():
        _gemini_cache = {}
        return _gemini_cache

    try:
        _gemini_cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _gemini_cache = {}
    return _gemini_cache


def _get_cached_gemini_value(cache_key):
    return _load_gemini_cache().get(cache_key)


def _set_cached_gemini_value(cache_key, value):
    if value is None:
        return

    cache = _load_gemini_cache()
    cache[cache_key] = value
    try:
        CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except OSError:
        pass


def _generation_config_for_model(model, generation_config):
    model_config = generation_config.copy()
    if "thinkingConfig" not in model_config:
        model_config["thinkingConfig"] = {"thinkingBudget": 0}
    return model_config


def _gemini_generate_text(prompt, generation_config):
    api_key = _get_gemini_api_key()
    if not api_key:
        return None

    for model in _gemini_models():
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": _generation_config_for_model(model, generation_config),
        }

        for attempt in range(MAX_RETRIES):
            try:
                response = httpx.post(
                    GEMINI_API_URL.format(model=model),
                    headers={
                        "x-goog-api-key": api_key,
                        "content-type": "application/json",
                    },
                    json=payload,
                    timeout=10,
                )
                response.raise_for_status()
                return _extract_gemini_text(response.json())
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                retryable = status_code in {429, 500, 502, 503, 504}
                if retryable and attempt < MAX_RETRIES - 1:
                    time.sleep(0.5 * (2**attempt))
                    continue
                break
            except httpx.HTTPError:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(0.5 * (2**attempt))
                    continue
                break

    return None


def _get_fatsecret_token():
    global _fatsecret_token, _fatsecret_token_expires_at

    client_id = os.getenv("FATSECRET_CLIENT_ID")
    client_secret = os.getenv("FATSECRET_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    if _fatsecret_token and time.time() < _fatsecret_token_expires_at:
        return _fatsecret_token

    response = httpx.post(
        FATSECRET_TOKEN_URL,
        data={"grant_type": "client_credentials", "scope": "basic"},
        auth=(client_id, client_secret),
        headers={"content-type": "application/x-www-form-urlencoded"},
        timeout=8,
    )
    response.raise_for_status()
    data = response.json()
    _fatsecret_token = data.get("access_token")
    _fatsecret_token_expires_at = time.time() + int(data.get("expires_in", 3600)) - 60
    return _fatsecret_token


def _first_item(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _get_fatsecret(food_name):
    token = _get_fatsecret_token()
    if not token:
        return None

    response = httpx.get(
        FATSECRET_SEARCH_URL,
        params={
            "search_expression": food_name.replace("_", " "),
            "max_results": 1,
            "format": "json",
            "region": "IN",
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=8,
    )
    response.raise_for_status()
    foods = response.json().get("foods", {})
    food = _first_item(foods.get("food"))
    if not food:
        return None

    serving = _first_item(food.get("servings", {}).get("serving"))
    if not serving:
        return None

    serving_description = serving.get("serving_description") or "serving"
    return {
        "serving": serving_description,
        "calories": _to_float(serving.get("calories")),
        "protein_g": _to_float(serving.get("protein")),
        "carbs_g": _to_float(serving.get("carbohydrate")),
        "fat_g": _to_float(serving.get("fat")),
        "source": "fatsecret",
    }


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


def _get_open_food_facts(food_name):
    response = httpx.get(
        OPEN_FOOD_FACTS_SEARCH_URL,
        params={
            "search_terms": food_name.replace("_", " "),
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": 1,
            "fields": "product_name,nutriments",
        },
        headers={"User-Agent": "SmartFoodNutritionAnalyzer/0.1"},
        timeout=8,
    )
    response.raise_for_status()
    products = response.json().get("products", [])
    if not products:
        return None

    nutriments = products[0].get("nutriments", {})
    calories = nutriments.get("energy-kcal_100g")
    if calories is None:
        calories = nutriments.get("energy-kcal")

    return {
        "serving": "100 g",
        "calories": calories,
        "protein_g": nutriments.get("proteins_100g"),
        "carbs_g": nutriments.get("carbohydrates_100g"),
        "fat_g": nutriments.get("fat_100g"),
        "source": "open_food_facts",
    }


def _parse_json_object(text):
    if not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _extract_number(data, keys):
    if not isinstance(data, dict):
        return None
    for k in keys:
        if k in data:
            v = data[k]
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v.replace("g", "").replace("kcal", "").strip())
                except ValueError:
                    pass
            if isinstance(v, dict):
                val = v.get("value") if "value" in v else v.get("total")
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, dict) and "value" in val and isinstance(val["value"], (int, float)):
                    return float(val["value"])
    for v in data.values():
        if isinstance(v, dict):
            res = _extract_number(v, keys)
            if res is not None:
                return res
    return None


def _get_gemini_nutrition(food_name):
    normalized_food = food_name.strip().lower()
    cache_key = f"nutrition:v3:{normalized_food}"
    cached_nutrition = _get_cached_gemini_value(cache_key)
    if isinstance(cached_nutrition, dict) and _has_any_nutrition_value(cached_nutrition):
        return cached_nutrition

    prompt = (
        "Estimate average nutrition for 1 standard serving of this food as JSON only. "
        "Use an Indian serving portion when relevant. "
        "Output ONLY a flat JSON object with these exact keys: "
        '{"serving": "1 serving", "calories": 250, "protein_g": 5, "carbs_g": 30, "fat_g": 12}. '
        f"Food item: {food_name.replace('_', ' ')}"
    )

    text = _gemini_generate_text(
        prompt,
        {
            "temperature": 0.1,
            "maxOutputTokens": 800,
            "responseMimeType": "application/json",
        },
    )
    data = _parse_json_object(text)
    if not data:
        return None

    calories = _extract_number(data, ["calories", "energy", "energy_kcal", "kcal"])
    protein = _extract_number(data, ["protein_g", "protein", "proteins"])
    carbs = _extract_number(data, ["carbs_g", "carbs", "carbohydrates", "carbohydrate"])
    fat = _extract_number(data, ["fat_g", "fat", "fats", "total_fat"])
    serving = data.get("serving") or data.get("serving_size") or "1 serving"

    nutrition = {
        "serving": str(serving),
        "calories": calories,
        "protein_g": protein,
        "carbs_g": carbs,
        "fat_g": fat,
        "source": "gemini_estimate",
    }
    if not _has_any_nutrition_value(nutrition):
        return None

    _set_cached_gemini_value(cache_key, nutrition)
    return nutrition


def get_nutrition(food_name):
    nutrition_results = []

    for provider in (
        _get_fatsecret,
        _get_usda,
        _get_open_food_facts,
        _get_gemini_nutrition,
    ):
        try:
            nutrition = provider(food_name)
        except httpx.HTTPError:
            nutrition = None

        if nutrition and _has_any_nutrition_value(nutrition):
            if _has_complete_nutrition(nutrition):
                return nutrition
            nutrition_results.append(nutrition)

    per_100g_results = [
        nutrition for nutrition in nutrition_results if _is_per_100g(nutrition)
    ]
    if per_100g_results:
        nutrition = per_100g_results[0]
        for extra_nutrition in per_100g_results[1:]:
            nutrition = _merge_missing_nutrition(nutrition, extra_nutrition)
            if _has_complete_nutrition(nutrition):
                return nutrition
        return nutrition

    if nutrition_results:
        return max(nutrition_results, key=_value_count)

    return _unavailable_nutrition()


def _extract_gemini_text(data):
    candidates = data.get("candidates", [])
    if not candidates:
        return None

    parts = candidates[0].get("content", {}).get("parts", [])
    text = " ".join(part.get("text", "") for part in parts).strip()
    return text or None


def _get_gemini_healthy_alternative(food_name):
    cache_key = f"healthy_alternative:v1:{food_name}"
    cached_alternative = _get_cached_gemini_value(cache_key)
    if isinstance(cached_alternative, str) and len(cached_alternative.strip()) >= 12:
        return cached_alternative

    prompt = (
        "Suggest one healthier alternative for this food in one short sentence. "
        "Start directly with a complete sentence like 'Choose ...' or 'Try ...'. "
        "Keep it practical for an Indian user when relevant. "
        "Do not include calorie numbers unless certain. "
        f"Food: {food_name.replace('_', ' ')}"
    )

    alternative = _gemini_generate_text(
        prompt,
        {
            "temperature": 0.4,
            "maxOutputTokens": 160,
        },
    )
    if not alternative or len(alternative.strip()) < 12:
        return None

    _set_cached_gemini_value(cache_key, alternative)
    return alternative


def get_healthy_alternative(food_name):
    normalized_food = food_name.strip().lower()
    if normalized_food in _healthy_alternative_cache:
        return _healthy_alternative_cache[normalized_food]

    try:
        alternative = _get_gemini_healthy_alternative(normalized_food)
    except httpx.HTTPError:
        alternative = None

    _healthy_alternative_cache[normalized_food] = alternative
    return alternative
