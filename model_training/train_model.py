from pathlib import Path

import tensorflow as tf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "model_training" / "dataset"
MODEL_OUTPUT_DIR = PROJECT_ROOT / "backend" / "saved_model"
MODEL_OUTPUT_PATH = MODEL_OUTPUT_DIR / "food_effnetb0.keras"
WEIGHTS_OUTPUT_PATH = MODEL_OUTPUT_DIR / "food_effnetb0.weights.h5"

IMAGE_SIZE = (224, 224)
BATCH_SIZE = 32
EPOCHS = 10
SEED = 42


def load_dataset(split_name, shuffle=True):
    split_dir = DATASET_DIR / split_name
    if not split_dir.exists():
        raise FileNotFoundError(
            f"Missing dataset folder: {split_dir}\n"
            "Expected structure: dataset/train, dataset/val, dataset/test"
        )

    return tf.keras.utils.image_dataset_from_directory(
        split_dir,
        image_size=IMAGE_SIZE,
        batch_size=BATCH_SIZE,
        shuffle=shuffle,
        seed=SEED,
    )


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

    model = tf.keras.Model(inputs, outputs, name="smart_food_effnetb0")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def main():
    train_ds = load_dataset("train")
    val_ds = load_dataset("val")
    test_ds = load_dataset("test", shuffle=False)

    class_names = train_ds.class_names
    print(f"Food classes: {class_names}")

    autotune = tf.data.AUTOTUNE
    train_ds = train_ds.prefetch(autotune)
    val_ds = val_ds.prefetch(autotune)
    test_ds = test_ds.prefetch(autotune)

    model = build_model(num_classes=len(class_names))
    model.summary()

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=3,
            restore_best_weights=True,
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=MODEL_OUTPUT_PATH,
            monitor="val_accuracy",
            save_best_only=True,
        ),
    ]

    model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=EPOCHS,
        callbacks=callbacks,
    )

    test_loss, test_accuracy = model.evaluate(test_ds)
    print(f"Test loss: {test_loss:.4f}")
    print(f"Test accuracy: {test_accuracy:.4f}")

    MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save(MODEL_OUTPUT_PATH)
    print(f"Saved model to: {MODEL_OUTPUT_PATH}")

    model.save_weights(WEIGHTS_OUTPUT_PATH)
    print(f"Saved model weights to: {WEIGHTS_OUTPUT_PATH}")

    labels_path = MODEL_OUTPUT_DIR / "class_names.txt"
    labels_path.write_text("\n".join(class_names), encoding="utf-8")
    print(f"Saved class names to: {labels_path}")


if __name__ == "__main__":
    main()
