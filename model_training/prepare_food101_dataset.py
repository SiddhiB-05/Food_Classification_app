import argparse
import random
import shutil
import zipfile
from pathlib import Path

import kagglehub


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "model_training" / "dataset"
DATASET_HANDLE = "dansbecker/food-101"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SEED = 42


def extract_zip_files(download_dir):
    for zip_path in Path(download_dir).rglob("*.zip"):
        extract_dir = zip_path.with_suffix("")
        if extract_dir.exists():
            continue
        print(f"Extracting: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)


def find_food101_root(download_dir):
    download_dir = Path(download_dir)
    candidates = [download_dir, *download_dir.rglob("food-101")]

    for candidate in candidates:
        if (
            (candidate / "images").exists()
            and (candidate / "meta" / "train.txt").exists()
            and (candidate / "meta" / "test.txt").exists()
        ):
            return candidate

    raise FileNotFoundError(
        "Could not find Food-101 structure with images/ and meta/train.txt. "
        f"Downloaded path was: {download_dir}"
    )


def read_split(meta_file):
    return [line.strip() for line in meta_file.read_text(encoding="utf-8").splitlines() if line.strip()]


def copy_image(src, dst, force=False):
    if dst.exists() and not force:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def prepare_dataset(food101_root, output_dir, val_ratio, max_classes=None, force=False):
    images_root = food101_root / "images"
    meta_root = food101_root / "meta"
    output_dir = Path(output_dir)

    train_items = read_split(meta_root / "train.txt")
    test_items = read_split(meta_root / "test.txt")

    all_classes = sorted({item.split("/")[0] for item in train_items})
    selected_classes = set(all_classes[:max_classes]) if max_classes else set(all_classes)

    rng = random.Random(SEED)
    class_to_train_items = {class_name: [] for class_name in selected_classes}
    for item in train_items:
        class_name, _ = item.split("/")
        if class_name in selected_classes:
            class_to_train_items[class_name].append(item)

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
        if class_name not in selected_classes:
            continue
        src = images_root / f"{item}.jpg"
        dst = output_dir / "test" / class_name / src.name
        copy_image(src, dst, force=force)

    print(f"Prepared Food-101 dataset at: {output_dir}")
    print(f"Classes: {len(selected_classes)}")
    print("Expected structure is ready: train/, val/, test/")


def main():
    parser = argparse.ArgumentParser(description="Download Food-101 from Kaggle and prepare train/val/test folders.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--max-classes", type=int, default=None, help="Optional quick test with first N classes.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing copied images.")
    args = parser.parse_args()

    print(f"Downloading Kaggle dataset: {DATASET_HANDLE}")
    download_path = kagglehub.dataset_download(DATASET_HANDLE)
    print(f"Path to dataset files: {download_path}")

    extract_zip_files(download_path)
    food101_root = find_food101_root(download_path)
    print(f"Food-101 root: {food101_root}")

    prepare_dataset(
        food101_root=food101_root,
        output_dir=args.output_dir,
        val_ratio=args.val_ratio,
        max_classes=args.max_classes,
        force=args.force,
    )


if __name__ == "__main__":
    main()
