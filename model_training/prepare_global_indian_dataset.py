import argparse
import random
import re
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
DEFAULT_INDIAN_HANDLES = [
    "iamsouravbanerjee/indian-food-images-dataset",
    "kashyap077/indian-food-images-for-model-fine-tuning-2026",
]
DEFAULT_MAX_IMAGES_PER_CLASS = 1200
DEFAULT_MIN_IMAGES_PER_CLASS = 40
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

IMPORTANT_INDIAN_CLASSES = [
    "biryani",
    "butter_chicken",
    "chole_bhature",
    "dhokla",
    "dosa",
    "fafda",
    "gulab_jamun",
    "idli",
    "jalebi",
    "khaman",
    "khandvi",
    "lassi",
    "medu_vada",
    "misal_pav",
    "modak",
    "momos",
    "naan",
    "pani_puri",
    "pav_bhaji",
    "poha",
    "rajma_chawal",
    "rasgulla",
    "samosa",
    "thepla",
    "undhiyu",
    "uttapam",
    "vada_pav",
]

CLASS_NAME_ALIASES = {
    "khaman_dhokla": "dhokla",
    "khaman": "dhokla",
    "medu_vada": "vada",
    "mendu_vada": "vada",
    "paani_puri": "pani_puri",
    "panipuri": "pani_puri",
    "gol_gappa": "pani_puri",
    "golgappa": "pani_puri",
    "momo": "momos",
    "steamed_momos": "momos",
}


def normalize_class_name(class_name):
    normalized = class_name.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return CLASS_NAME_ALIASES.get(normalized, normalized)


def source_slug(source_name):
    return normalize_class_name(str(source_name).split("/")[-1])[:60] or "source"


def split_values(values):
    items = []
    for value in values or []:
        for item in str(value).split(","):
            item = item.strip()
            if item and item not in items:
                items.append(item)
    return items


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


def clean_output_dir(output_dir):
    output_dir = Path(output_dir)
    if output_dir.exists():
        print(f"Cleaning existing dataset folder: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


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


def prepare_indian_dataset(
    indian_root,
    output_dir,
    val_ratio,
    test_ratio,
    max_classes=None,
    min_images_per_class=DEFAULT_MIN_IMAGES_PER_CLASS,
    max_images_per_class=DEFAULT_MAX_IMAGES_PER_CLASS,
    force=False,
    source_name="indian",
):
    output_dir = Path(output_dir)
    rng = random.Random(SEED)
    copied_classes = 0
    skipped_classes = []
    source_prefix = source_slug(source_name)

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
        if len(image_paths) < min_images_per_class:
            skipped_classes.append((class_name, len(image_paths)))
            continue

        rng.shuffle(image_paths)
        if max_images_per_class and len(image_paths) > max_images_per_class:
            image_paths = image_paths[:max_images_per_class]

        test_count = max(1, int(len(image_paths) * test_ratio))
        val_count = max(1, int(len(image_paths) * val_ratio))

        split_items = {
            "test": image_paths[:test_count],
            "val": image_paths[test_count : test_count + val_count],
            "train": image_paths[test_count + val_count :],
        }

        for split_name, split_paths in split_items.items():
            for index, src in enumerate(split_paths, start=1):
                dst = (
                    output_dir
                    / split_name
                    / class_name
                    / f"{source_prefix}_{class_name}_{index:05d}{src.suffix.lower()}"
                )
                copy_image(src, dst, force=force)

        copied_classes += 1

    print(f"Added Indian dataset classes from {source_name}: {copied_classes}")
    if skipped_classes:
        preview = ", ".join(f"{name}({count})" for name, count in skipped_classes[:10])
        print(
            f"Skipped {len(skipped_classes)} low-image classes from {source_name} "
            f"below min_images_per_class={min_images_per_class}: {preview}"
        )


def summarize_prepared_dataset(output_dir):
    output_dir = Path(output_dir)
    train_dir = output_dir / "train"
    if not train_dir.exists():
        return

    class_counts = {
        class_dir.name: count_image_files(class_dir)
        for class_dir in train_dir.iterdir()
        if class_dir.is_dir()
    }
    missing_important = [
        class_name
        for class_name in IMPORTANT_INDIAN_CLASSES
        if normalize_class_name(class_name) not in class_counts
    ]

    print("\nPrepared dataset summary")
    print(f"Train classes: {len(class_counts)}")
    if class_counts:
        counts = sorted(class_counts.values())
        print(f"Train images per class: min={counts[0]}, median={counts[len(counts) // 2]}, max={counts[-1]}")
    if missing_important:
        print("Important Indian classes still missing:")
        print(", ".join(missing_important))
    else:
        print("Important Indian class coverage looks good.")


def main():
    parser = argparse.ArgumentParser(description="Prepare combined Food-101 + Indian food dataset.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--indian-handle",
        action="append",
        default=[],
        help="Kaggle Indian dataset handle. Can be passed more than once. Kept for backwards compatibility.",
    )
    parser.add_argument(
        "--indian-handles",
        nargs="*",
        default=None,
        help="One or more Kaggle Indian dataset handles. Comma-separated values are also accepted.",
    )
    parser.add_argument(
        "--local-indian-roots",
        nargs="*",
        default=[],
        help="Optional local ImageFolder roots, useful for manually downloaded datasets like Khana.",
    )
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
    parser.add_argument("--min-images-per-class", type=int, default=DEFAULT_MIN_IMAGES_PER_CLASS)
    parser.add_argument("--max-images-per-class", type=int, default=DEFAULT_MAX_IMAGES_PER_CLASS)
    parser.add_argument("--clean-output", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.clean_output:
        clean_output_dir(args.output_dir)

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

    indian_handles = split_values(args.indian_handles) + split_values(args.indian_handle)
    if not indian_handles:
        indian_handles = DEFAULT_INDIAN_HANDLES

    for indian_handle in indian_handles:
        print(f"Downloading Indian food dataset: {indian_handle}")
        indian_path = kagglehub.dataset_download(indian_handle)
        extract_zip_files(indian_path)
        indian_root = find_imagefolder_root(indian_path)
        print(f"Indian dataset root: {indian_root}")
        prepare_indian_dataset(
            indian_root=indian_root,
            output_dir=args.output_dir,
            val_ratio=args.val_ratio,
            test_ratio=args.test_ratio,
            max_classes=args.max_indian_classes,
            min_images_per_class=args.min_images_per_class,
            max_images_per_class=args.max_images_per_class,
            force=args.force,
            source_name=indian_handle,
        )

    for local_root in split_values(args.local_indian_roots):
        local_root = Path(local_root)
        print(f"Adding local Indian dataset root: {local_root}")
        indian_root = find_imagefolder_root(local_root)
        prepare_indian_dataset(
            indian_root=indian_root,
            output_dir=args.output_dir,
            val_ratio=args.val_ratio,
            test_ratio=args.test_ratio,
            max_classes=args.max_indian_classes,
            min_images_per_class=args.min_images_per_class,
            max_images_per_class=args.max_images_per_class,
            force=args.force,
            source_name=local_root.name,
        )

    print(f"Prepared combined dataset at: {args.output_dir}")
    print("Expected structure is ready: train/, val/, test/")
    summarize_prepared_dataset(args.output_dir)


if __name__ == "__main__":
    main()
