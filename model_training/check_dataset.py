from pathlib import Path


DATASET_DIR = Path(__file__).resolve().parent / "dataset"
SPLITS = ["train", "val", "test"]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def count_images(folder):
    return sum(
        1
        for file_path in folder.iterdir()
        if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS
    )


def get_class_folders(split_dir):
    if not split_dir.exists():
        return []
    return sorted(path.name for path in split_dir.iterdir() if path.is_dir())


def main():
    if not DATASET_DIR.exists():
        raise FileNotFoundError(f"Dataset folder not found: {DATASET_DIR}")

    split_classes = {}
    has_error = False

    for split in SPLITS:
        split_dir = DATASET_DIR / split
        classes = get_class_folders(split_dir)
        split_classes[split] = classes

        print(f"\n{split.upper()}")
        print("-" * len(split))

        if not split_dir.exists():
            print(f"Missing folder: {split_dir}")
            has_error = True
            continue

        if not classes:
            print("No class folders found.")
            has_error = True
            continue

        for class_name in classes:
            class_dir = split_dir / class_name
            image_count = count_images(class_dir)
            print(f"{class_name}: {image_count} images")

            if image_count == 0:
                has_error = True

    train_classes = set(split_classes.get("train", []))
    for split in ["val", "test"]:
        current_classes = set(split_classes.get(split, []))
        if current_classes != train_classes:
            print(f"\nClass mismatch between train and {split}.")
            print(f"Only in train: {sorted(train_classes - current_classes)}")
            print(f"Only in {split}: {sorted(current_classes - train_classes)}")
            has_error = True

    if has_error:
        print("\nDataset check finished with warnings.")
        print("Add images to every class folder before training.")
    else:
        print("\nDataset check passed. You are ready to train.")


if __name__ == "__main__":
    main()
