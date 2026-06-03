from pathlib import Path
from urllib.parse import urlparse

import requests


DATASET_DIR = Path(__file__).resolve().parent / "dataset"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
USER_AGENT = "SmartFoodNutritionAnalyzer/0.1"
CLASS_NAME = "salad"
TARGETS = {"train": 30, "val": 10, "test": 10}


def existing_count():
    count = 0
    for split in TARGETS:
        folder = DATASET_DIR / split / CLASS_NAME
        count += sum(
            1
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
    return count


def split_for_index(index):
    if index < TARGETS["train"]:
        return "train"
    if index < TARGETS["train"] + TARGETS["val"]:
        return "val"
    return "test"


def search_urls(search_term, offset):
    response = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrsearch": search_term,
            "gsrlimit": "20",
            "gsroffset": str(offset),
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "iiurlwidth": "320",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})

    urls = []
    for page in pages.values():
        info = page.get("imageinfo", [{}])[0]
        url = info.get("thumburl") or info.get("url")
        if url and info.get("mime", "").startswith("image/"):
            urls.append(url)
    return urls


def download(url, output_path):
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    if not response.headers.get("Content-Type", "").startswith("image/"):
        return False
    output_path.write_bytes(response.content)
    return True


def main():
    for split in TARGETS:
        (DATASET_DIR / split / CLASS_NAME).mkdir(parents=True, exist_ok=True)

    saved = existing_count()
    needed = sum(TARGETS.values())
    seen = set()
    offset = 0
    search_terms = [
        "salad food",
        "green salad",
        "caesar salad",
        "vegetable salad",
        "greek salad",
    ]

    for term in search_terms:
        offset = 0
        while saved < needed and offset < 120:
            print(f"searching {term}, offset {offset}", flush=True)
            for url in search_urls(term, offset):
                if saved >= needed:
                    break
                if url in seen:
                    continue
                seen.add(url)

                suffix = Path(urlparse(url).path).suffix.lower()
                if suffix not in IMAGE_EXTENSIONS:
                    suffix = ".jpg"

                split = split_for_index(saved)
                output_path = DATASET_DIR / split / CLASS_NAME / f"{CLASS_NAME}_{saved + 1:03d}{suffix}"
                try:
                    if download(url, output_path):
                        saved += 1
                        print(f"saved salad {saved}/{needed}", flush=True)
                except Exception as exc:
                    print(f"skip {type(exc).__name__}", flush=True)
                    if output_path.exists():
                        output_path.unlink()
            offset += 20

    print(f"done: {saved}/{needed}", flush=True)


if __name__ == "__main__":
    main()
