import time
from pathlib import Path
from urllib.parse import urlparse

import requests


DATASET_DIR = Path(__file__).resolve().parent / "dataset"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
USER_AGENT = "SmartFoodNutritionAnalyzer/0.1"

FOODISH_BASE_URL = "https://foodish-api.com"
FOOD_CLASSES = {
    "pizza": "pizza",
    "burger": "burger",
}
COMMONS_SEARCH_TERMS = {
    "salad": "salad food",
}

SPLIT_TARGETS = {
    "train": 30,
    "val": 10,
    "test": 10,
}


def prepare_folders():
    for split in SPLIT_TARGETS:
        for class_name in FOOD_CLASSES:
            (DATASET_DIR / split / class_name).mkdir(parents=True, exist_ok=True)


def split_for_index(index):
    train_end = SPLIT_TARGETS["train"]
    val_end = train_end + SPLIT_TARGETS["val"]
    if index < train_end:
        return "train"
    if index < val_end:
        return "val"
    return "test"


def existing_images(class_name):
    images = []
    for split in SPLIT_TARGETS:
        class_dir = DATASET_DIR / split / class_name
        if not class_dir.exists():
            continue
        images.extend(
            path
            for path in class_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
    return images


def get_random_foodish_image(foodish_category):
    response = requests.get(
        f"{FOODISH_BASE_URL}/api/images/{foodish_category}",
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data["image"]


def download_image(url, output_path):
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if not content_type.startswith("image/"):
        return False
    output_path.write_bytes(response.content)
    return True


def download_class_images(class_name, foodish_category):
    needed = sum(SPLIT_TARGETS.values())
    current_count = len(existing_images(class_name))
    if current_count >= needed:
        print(f"{class_name}: already has {current_count} images, skipping")
        return

    seen_urls = set()
    saved = current_count
    attempts = 0
    max_attempts = needed * 8

    while saved < needed and attempts < max_attempts:
        attempts += 1
        try:
            image_url = get_random_foodish_image(foodish_category)
            if image_url in seen_urls:
                continue
            seen_urls.add(image_url)

            suffix = Path(urlparse(image_url).path).suffix.lower()
            if suffix not in IMAGE_EXTENSIONS:
                suffix = ".jpg"

            split = split_for_index(saved)
            output_path = DATASET_DIR / split / class_name / f"{class_name}_{saved + 1:03d}{suffix}"
            if download_image(image_url, output_path):
                saved += 1
                print(f"{class_name}: saved {saved}/{needed}")
                time.sleep(0.25)
        except Exception as exc:
            print(f"{class_name}: skipped one image - {type(exc).__name__}")
            time.sleep(1)

    if saved < needed:
        print(f"{class_name}: only downloaded {saved}/{needed} images")


def commons_search_images(search_term, limit=80):
    response = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrsearch": search_term,
            "gsrlimit": str(limit),
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "iiurlwidth": "512",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})

    urls = []
    for page in pages.values():
        image_info = page.get("imageinfo", [{}])[0]
        mime = image_info.get("mime", "")
        url = image_info.get("thumburl") or image_info.get("url")
        if url and mime in {"image/jpeg", "image/png", "image/webp"}:
            urls.append(url)
    return list(dict.fromkeys(urls))


def download_commons_class_images(class_name, search_term):
    needed = sum(SPLIT_TARGETS.values())
    current_count = len(existing_images(class_name))
    if current_count >= needed:
        print(f"{class_name}: already has {current_count} images, skipping")
        return

    saved = current_count
    urls = commons_search_images(search_term)

    for image_url in urls:
        if saved >= needed:
            break

        suffix = Path(urlparse(image_url).path).suffix.lower()
        if suffix not in IMAGE_EXTENSIONS:
            suffix = ".jpg"

        split = split_for_index(saved)
        output_path = DATASET_DIR / split / class_name / f"{class_name}_{saved + 1:03d}{suffix}"

        try:
            if download_image(image_url, output_path):
                saved += 1
                print(f"{class_name}: saved {saved}/{needed}")
                time.sleep(1.5)
        except Exception as exc:
            print(f"{class_name}: skipped one image - {type(exc).__name__}")
            if output_path.exists():
                output_path.unlink()
            time.sleep(3)

    if saved < needed:
        print(f"{class_name}: only downloaded {saved}/{needed} images")


def main():
    prepare_folders()
    for class_name, foodish_category in FOOD_CLASSES.items():
        download_class_images(class_name, foodish_category)
    for class_name, search_term in COMMONS_SEARCH_TERMS.items():
        download_commons_class_images(class_name, search_term)


if __name__ == "__main__":
    main()
