import base64
from io import BytesIO
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
_base_grad_model = None


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


def _call_layer(layer, inputs):
    try:
        return layer(inputs, training=False)
    except TypeError:
        return layer(inputs)


def get_base_grad_model():
    global _base_grad_model

    if _base_grad_model is None:
        model, _ = get_model()
        base_model = model.get_layer("efficientnetb0")
        target_layer = base_model.get_layer("top_activation")
        _base_grad_model = tf.keras.Model(
            base_model.inputs,
            [target_layer.output, base_model.output],
            name="efficientnetb0_gradcam",
        )

    return _base_grad_model


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


def _classifier_head_from_base_output(model, base_output):
    output = base_output
    use_head = False
    for layer in model.layers:
        if use_head:
            output = _call_layer(layer, output)
        if layer.name == "efficientnetb0":
            use_head = True
    return output


def _enhance_heatmap(heatmap):
    heatmap = np.nan_to_num(heatmap, nan=0.0, posinf=0.0, neginf=0.0)
    heatmap = np.clip(heatmap, 0.0, None)
    max_value = heatmap.max()
    if max_value <= 0:
        return np.zeros_like(heatmap)

    heatmap = heatmap / max_value
    active_values = heatmap[heatmap > 0]
    if active_values.size:
        floor = np.percentile(active_values, 45)
        if 0 < floor < 1:
            heatmap = np.clip((heatmap - floor) / (1 - floor), 0, 1)

    return np.power(heatmap, 0.7)


def _heatmap_to_color(heatmap):
    red = np.clip(2.2 * heatmap, 0, 1)
    green = np.clip(2.2 * heatmap - 0.65, 0, 1)
    blue = np.clip(2.2 * heatmap - 1.65, 0, 1) * 0.35
    return np.stack([red, green, blue], axis=-1) * 255.0


def _heatmap_to_overlay(image, heatmap):
    image = image.convert("RGB")
    image_array = np.array(image, dtype=np.float32)

    heatmap_image = Image.fromarray(np.uint8(255 * heatmap)).resize(
        image.size,
        Image.Resampling.BILINEAR,
    )
    heatmap_array = np.array(heatmap_image, dtype=np.float32) / 255.0
    heatmap_array = _enhance_heatmap(heatmap_array)

    color_map = _heatmap_to_color(heatmap_array)
    focus_strength = heatmap_array[..., None]
    dimmed_image = image_array * (0.38 + 0.62 * focus_strength)

    alpha = np.clip(0.18 + 0.72 * focus_strength, 0, 0.9)
    alpha = np.where(focus_strength > 0.04, alpha, 0)
    overlay = dimmed_image * (1 - alpha) + color_map * alpha
    overlay = np.clip(overlay, 0, 255).astype(np.uint8)

    buffer = BytesIO()
    Image.fromarray(overlay).save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def generate_gradcam(image, class_index=None):
    model, _ = get_model()
    base_grad_model = get_base_grad_model()
    image_batch = preprocess_image(image)

    with tf.GradientTape() as tape:
        augmented = model.get_layer("data_augmentation")(image_batch, training=False)
        conv_outputs, base_output = base_grad_model(augmented, training=False)
        tape.watch(conv_outputs)
        predictions = _classifier_head_from_base_output(model, base_output)
        if class_index is None:
            class_index = tf.argmax(predictions[0])
        class_score = predictions[:, class_index]

    gradients = tape.gradient(class_score, conv_outputs)
    if gradients is None:
        raise ValueError("Could not calculate Grad-CAM gradients.")

    pooled_gradients = tf.reduce_mean(gradients, axis=(0, 1, 2))
    conv_outputs = conv_outputs[0]
    heatmap = tf.reduce_sum(conv_outputs * pooled_gradients, axis=-1)
    heatmap = tf.maximum(heatmap, 0)
    max_value = tf.reduce_max(heatmap)
    if float(max_value) == 0:
        heatmap = tf.zeros_like(heatmap)
    else:
        heatmap = heatmap / max_value

    return _heatmap_to_overlay(image, heatmap.numpy())


def open_image_from_bytes(image_bytes):
    try:
        return Image.open(image_bytes)
    except Exception as exc:
        raise ValueError("Uploaded file is not a valid image.") from exc
