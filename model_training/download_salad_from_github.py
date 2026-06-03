from pathlib import Path

import requests


DATASET_DIR = Path(__file__).resolve().parent / "dataset"
USER_AGENT = "SmartFoodNutritionAnalyzer/0.1"
GITHUB_API = "https://api.github.com/repos/NavdeepSinghh/HealthDataset/contents"
CLASS_NAME = "salad"
TARGETS = {"train": 30, "val": 10, "test": 10}


def list_github_files(split):
    response = requests.get(
        f"{GITHUB_API}/{split}/{CLASS_NAME}",
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    return [
        item
        for item in response.json()
        if item.get("type") == "file" and item.get("download_url")
    ]


def existing_count(split):
    folder = DATASET_DIR / split / CLASS_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return sum(1 for path in folder.iterdir() if path.is_file())


def download_file(url, output_path):
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    output_path.write_bytes(response.content)


def main():
    for split, target in TARGETS.items():
        folder = DATASET_DIR / split / CLASS_NAME
        folder.mkdir(parents=True, exist_ok=True)

        current = existing_count(split)
        if current >= target:
            print(f"{split}/{CLASS_NAME}: already has {current}, skipping", flush=True)
            continue

        files = list_github_files(split)
        saved = current

        for item in files:
            if saved >= target:
                break

            suffix = Path(item["name"]).suffix or ".jpg"
            output_path = folder / f"{CLASS_NAME}_{saved + 1:03d}{suffix}"
            if output_path.exists():
                saved += 1
                continue

            download_file(item["download_url"], output_path)
            saved += 1
            print(f"{split}/{CLASS_NAME}: saved {saved}/{target}", flush=True)

        if saved < target:
            print(f"{split}/{CLASS_NAME}: only saved {saved}/{target}", flush=True)


if __name__ == "__main__":
    main()
