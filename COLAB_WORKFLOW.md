# Food-101 Colab Training Workflow

Use this workflow when moving from the current 3-class demo to the full Food-101 Kaggle dataset.

## VS Code: before Colab

1. Push only source code to GitHub.
2. Do not push local datasets, virtual environments, or trained model files.
3. Keep these small files in the repo:
   - `backend/main.py`
   - `backend/model_loader.py`
   - `backend/nutrition_data.py`
   - `backend/requirements.txt`
   - `backend/.env.example`
   - `model_training/train_model.py`
   - `model_training/test_model.py`

## Colab: setup

Run these cells in Google Colab with GPU enabled.

```python
!git clone https://github.com/<your-username>/CNN_project.git
%cd CNN_project
```

Install Colab training dependencies:

```python
!pip install -r model_training/requirements-colab.txt
```

Download Food-101 from Kaggle and prepare `train/val/test` folders:

```python
!python model_training/prepare_food101_dataset.py
```

For a fast test run before full training, use only a few classes:

```python
!python model_training/prepare_food101_dataset.py --max-classes 5
```

The project training script expects this structure, and the prepare script creates it:

```text
model_training/dataset/
  train/
  val/
  test/
```

## Colab: train

```python
!python model_training/train_model.py
```

The output files will be created here:

```text
backend/saved_model/food_effnetb0.keras
backend/saved_model/food_effnetb0.weights.h5
backend/saved_model/class_names.txt
```

Download these two for VS Code:

```python
from google.colab import files

files.download("backend/saved_model/food_effnetb0.keras")
files.download("backend/saved_model/class_names.txt")
```

## VS Code: after Colab

Place downloaded files here:

```text
backend/saved_model/food_effnetb0.keras
backend/saved_model/class_names.txt
```

Install backend dependencies:

```powershell
cd backend
pip install -r requirements.txt
```

Run API:

```powershell
uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Nutrition API keys

Copy `backend/.env.example` to `backend/.env` locally and fill whichever provider you want:

```text
NUTRITIONIX_APP_ID=...
NUTRITIONIX_API_KEY=...
USDA_API_KEY=...
```

The backend checks Nutritionix first, then USDA FoodData Central, then local demo estimates.
