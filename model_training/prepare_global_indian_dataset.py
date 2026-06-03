import argparse
import random
import shutil
import zipfile
from pathlib import Path

import kagglehub

from prepare_food101_dataset import (
    DATASET_HANDLE as FOOD101_HANDLE,
    IMAGE_EXTENSIONS,
    extract_zip_files,
    find_food101_root,
    prepare_dataset as prepare_food101,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "model_training" / "dataset"
DEFAULT_INDIAN_HANDLE = "iamsouravbanerjee/indian-food-images-dataset"
SEED = 42

SELECTED_FOOD101_CLASSES = [
    "apple_pie",
    "baby_back_ribs",
    "baklava",
    "breakfast_burrito",
    "bruschetta",
    "caesar_salad",
    "carrot_cake",
    "cheesecake",
    "chicken_curry",
    "chicken_quesadilla",
    "chicken_wings",
    "chocolate_cake",
    "chocolate_mousse",
    "churros",
    "club_sandwich",
    "creme_brulee",
    "cup_cakes",
    "donuts",
    "dumplings",
    "eggs_benedict",
    "falafel",
    "fish_and_chips",
    "french_fries",
    "french_toast",
    "fried_rice",
    "frozen_yogurt",
    "garlic_bread",
    "greek_salad",
    "grilled_cheese_sandwich",
    "grilled_salmon",
    "guacamole",
    "hamburger",
    "hot_dog",
    "hummus",
    "ice_cream",
    "lasagna",
    "macaroni_and_cheese",
    "miso_soup",
    "nachos",
    "omelette",
    "onion_rings",
    "pad_thai",
    "pancakes",
    "panna_cotta",
    "pizza",
    "ramen",
    "ravioli",
    "red_velvet_cake",
    "risotto",
    "samosa",
    "spaghetti_bolognese",
    "spaghetti_carbonara",
    "spring_rolls",
    "steak",
    "sushi",
    "tacos",
    "tiramisu",
    "waffles",
]


def normalize_class_name(class_name):
    return (
        class_name.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("__", "_")
    )


def extract_zip_files(download_dir):
    for zip_path in Path(download_dir).rglob("*.zip"):
        extract_dir = zip_path.with_suffix("")
        if extract_dir.exists():
            continue
        print(f"Extracting: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)


def count_image_files(class_dir):
    return sum(1 for item in class_dir.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS)


def find_imagefolder_root(download_dir, min_classes=5):
    download_dir = Path(download_dir)
    best_root = None
    best_score = 0

    for candidate in [download_dir, *download_dir.rglob("*")]:
        if not candidate.is_dir():
            continue

        class_dirs = [
            child
            for child in candidate.iterdir()
            if child.is_dir() and count_image_files(child) > 0
        ]
        if len(class_dirs) >= min_classes:
            score = sum(count_image_files(class_dir) for class_dir in class_dirs)
            if score > best_score:
                best_root = candidate
                best_score = score

    if best_root is None:
        raise FileNotFoundError(
            "Could not find an ImageFolder-style Indian dataset root. "
            "Expected one folder per class with images inside."
        )

    return best_root


def copy_image(src, dst, force=False):
    if dst.exists() and not force:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def prepare_selected_food101(food101_root, output_dir, selected_classes, val_ratio, force=False):
    selected_classes = set(selected_classes)
    images_root = food101_root / "images"
    meta_root = food101_root / "meta"
    output_dir = Path(output_dir)
    rng = random.Random(SEED)

    train_items = [
        line.strip()
        for line in (meta_root / "train.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and line.split("/")[0] in selected_classes
    ]
    test_items = [
        line.strip()
        for line in (meta_root / "test.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and line.split("/")[0] in selected_classes
    ]

    class_to_train_items = {}
    for item in train_items:
        class_name, _ = item.split("/")
        class_to_train_items.setdefault(class_name, []).append(item)

    for class_name, items in sorted(class_to_train_items.items()):
        rng.shuffle(items)
        val_count = max(1, int(len(items) * val_ratio))
        val_items = set(items[:val_count])

        for item in items:
            split = "val" if item in val_items else "train"
            src = images_root / f"{item}.jpg"
            dst = output_dir / split / class_name / src.name
            copy_image(src, dst, force=force)

    for item in test_items:
        class_name, _ = item.split("/")
        src = images_root / f"{item}.jpg"
        dst = output_dir / "test" / class_name / src.name
        copy_image(src, dst, force=force)

    print(f"Added selected Food-101 classes: {len(class_to_train_items)}")


def prepare_indian_dataset(indian_root, output_dir, val_ratio, test_ratio, max_classes=None, force=False):
    output_dir = Path(output_dir)
    rng = random.Random(SEED)

    class_dirs = sorted(
        [
            class_dir
            for class_dir in Path(indian_root).iterdir()
            if class_dir.is_dir() and count_image_files(class_dir) > 0
        ],
        key=lambda path: path.name.lower(),
    )
    if max_classes:
        class_dirs = class_dirs[:max_classes]

    for class_dir in class_dirs:
        class_name = normalize_class_name(class_dir.name)
        image_paths = [
            image_path
            for image_path in class_dir.iterdir()
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS
        ]
        rng.shuffle(image_paths)

        test_count = max(1, int(len(image_paths) * test_ratio))
        val_count = max(1, int(len(image_paths) * val_ratio))

        split_items = {
            "test": image_paths[:test_count],
            "val": image_paths[test_count : test_count + val_count],
            "train": image_paths[test_count + val_count :],
        }

        for split_name, split_paths in split_items.items():
            for index, src in enumerate(split_paths, start=1):
                dst = output_dir / split_name / class_name / f"{class_name}_{index:05d}{src.suffix.lower()}"
                copy_image(src, dst, force=force)

    print(f"Added Indian dataset classes: {len(class_dirs)}")


def main():
    parser = argparse.ArgumentParser(description="Prepare combined Food-101 + Indian food dataset.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--indian-handle", default=DEFAULT_INDIAN_HANDLE)
    parser.add_argument(
        "--food101-mode",
        choices=["selected", "all"],
        default="selected",
        help="Use selected common global classes or all Food-101 classes.",
    )
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--max-food101-classes", type=int, default=None)
    parser.add_argument("--max-indian-classes", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    print(f"Downloading Food-101 dataset: {FOOD101_HANDLE}")
    food101_path = kagglehub.dataset_download(FOOD101_HANDLE)
    extract_zip_files(food101_path)
    food101_root = find_food101_root(food101_path)
    if args.food101_mode == "all":
        prepare_food101(
            food101_root=food101_root,
            output_dir=args.output_dir,
            val_ratio=args.val_ratio,
            max_classes=args.max_food101_classes,
            force=args.force,
        )
    else:
        selected_classes = SELECTED_FOOD101_CLASSES
        if args.max_food101_classes:
            selected_classes = selected_classes[: args.max_food101_classes]
        prepare_selected_food101(
            food101_root=food101_root,
            output_dir=args.output_dir,
            selected_classes=selected_classes,
            val_ratio=args.val_ratio,
            force=args.force,
        )

    print(f"Downloading Indian food dataset: {args.indian_handle}")
    indian_path = kagglehub.dataset_download(args.indian_handle)
    extract_zip_files(indian_path)
    indian_root = find_imagefolder_root(indian_path)
    print(f"Indian dataset root: {indian_root}")
    prepare_indian_dataset(
        indian_root=indian_root,
        output_dir=args.output_dir,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        max_classes=args.max_indian_classes,
        force=args.force,
    )

    print(f"Prepared combined dataset at: {args.output_dir}")
    print("Expected structure is ready: train/, val/, test/")


if __name__ == "__main__":
    main()
