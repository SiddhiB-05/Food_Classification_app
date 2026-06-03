from pathlib import Path

import numpy as np
import tensorflow as tf
from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parent
SAVED_MODEL_DIR = BACKEND_DIR / "saved_model"
MODEL_PATH = SAVED_MODEL_DIR / "food_effnetb0.keras"
WEIGHTS_PATH = SAVED_MODEL_DIR / "food_effnetb0.weights.h5"
CLASS_NAMES_PATH = SAVED_MODEL_DIR / "class_names.txt"

IMAGE_SIZE = (224, 224)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

_model = None
_class_names = None


def load_class_names():
    if not CLASS_NAMES_PATH.exists():
        raise FileNotFoundError(f"Class names file not found: {CLASS_NAMES_PATH}")
    return CLASS_NAMES_PATH.read_text(encoding="utf-8").splitlines()


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


def get_model():
    global _model, _class_names

    if _model is None:
        _class_names = load_class_names()

        if MODEL_PATH.exists():
            _model = tf.keras.models.load_model(MODEL_PATH, compile=False)
        elif WEIGHTS_PATH.exists():
            _model = build_model(num_classes=len(_class_names))
            _model.load_weights(WEIGHTS_PATH)
        else:
            raise FileNotFoundError(
                f"Model file not found: {MODEL_PATH}. "
                f"Fallback weights file also not found: {WEIGHTS_PATH}"
            )

    return _model, _class_names


def preprocess_image(image):
    image = image.convert("RGB")
    image = image.resize(IMAGE_SIZE)
    image_array = np.array(image, dtype=np.float32)
    return np.expand_dims(image_array, axis=0)


def predict_food(image):
    model, class_names = get_model()
    image_batch = preprocess_image(image)

    probabilities = model.predict(image_batch, verbose=0)[0]
    predicted_index = int(np.argmax(probabilities))
    predicted_class = class_names[predicted_index]
    confidence = float(probabilities[predicted_index])

    return {
        "food": predicted_class,
        "confidence": round(confidence, 4),
        "scores": {
            class_name: round(float(score), 4)
            for class_name, score in zip(class_names, probabilities)
        },
    }


def open_image_from_bytes(image_bytes):
    try:
        return Image.open(image_bytes)
    except Exception as exc:
        raise ValueError("Uploaded file is not a valid image.") from exc
