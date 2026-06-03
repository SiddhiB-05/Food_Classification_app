import argparse
from pathlib import Path

import numpy as np
import tensorflow as tf
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "backend" / "saved_model" / "food_effnetb0.keras"
WEIGHTS_PATH = PROJECT_ROOT / "backend" / "saved_model" / "food_effnetb0.weights.h5"
CLASS_NAMES_PATH = PROJECT_ROOT / "backend" / "saved_model" / "class_names.txt"
DATASET_DIR = PROJECT_ROOT / "model_training" / "dataset"
IMAGE_SIZE = (224, 224)


def load_class_names():
    if not CLASS_NAMES_PATH.exists():
        raise FileNotFoundError(f"Class names file not found: {CLASS_NAMES_PATH}")
    return CLASS_NAMES_PATH.read_text(encoding="utf-8").splitlines()


def find_default_image():
    for image_path in (DATASET_DIR / "test").rglob("*"):
        if image_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            return image_path
    raise FileNotFoundError("No test image found in dataset/test")


def preprocess_image(image_path):
    image = Image.open(image_path).convert("RGB")
    image = image.resize(IMAGE_SIZE)
    image_array = np.array(image, dtype=np.float32)
    return np.expand_dims(image_array, axis=0)


def build_model(num_classes):
    data_augmentation = tf.keras.Sequential(
        [
            tf.keras.layers.RandomFlip("horizontal"),
            tf.keras.layers.RandomRotation(0.08),
            tf.keras.layers.RandomZoom(0.1),
            tf.keras.layers.RandomContrast(0.1),
        ],
        name="data_augmentation",
    )

    base_model = tf.keras.applications.EfficientNetB0(
        include_top=False,
        weights="imagenet",
        input_shape=(*IMAGE_SIZE, 3),
    )
    base_model.trainable = False

    inputs = tf.keras.Input(shape=(*IMAGE_SIZE, 3))
    x = data_augmentation(inputs)
    x = tf.keras.applications.efficientnet.preprocess_input(x)
    x = base_model(x, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.3)(x)
    outputs = tf.keras.layers.Dense(num_classes, activation="softmax")(x)
    return tf.keras.Model(inputs, outputs, name="smart_food_effnetb0")


def predict(image_path):
    class_names = load_class_names()

    if WEIGHTS_PATH.exists():
        model = build_model(num_classes=len(class_names))
        model.load_weights(WEIGHTS_PATH)
    elif MODEL_PATH.exists():
        model = tf.keras.models.load_model(MODEL_PATH, compile=False)
    else:
        raise FileNotFoundError(
            f"Model weights not found: {WEIGHTS_PATH}\n"
            f"Full model also not found: {MODEL_PATH}"
        )

    image_batch = preprocess_image(image_path)

    probabilities = model.predict(image_batch, verbose=0)[0]
    predicted_index = int(np.argmax(probabilities))
    predicted_class = class_names[predicted_index]
    confidence = float(probabilities[predicted_index])

    print(f"Image: {image_path}")
    print(f"Prediction: {predicted_class}")
    print(f"Confidence: {confidence:.2%}")
    print("\nAll scores:")
    for class_name, score in zip(class_names, probabilities):
        print(f"{class_name}: {float(score):.2%}")


def main():
    parser = argparse.ArgumentParser(description="Test the trained food image model.")
    parser.add_argument(
        "--image",
        type=Path,
        default=None,
        help="Path to an image. If omitted, one image from dataset/test is used.",
    )
    args = parser.parse_args()

    image_path = args.image or find_default_image()
    predict(image_path)


if __name__ == "__main__":
    main()
