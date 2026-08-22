---
title: Smart Food Nutrition Analyzer API
emoji: 🥗
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Smart Food Nutrition Analyzer

A full-stack AI-powered food analysis platform that identifies food items from images, estimates nutritional values, provides healthier alternatives, and tracks daily meal intake.

## Features

* Food image classification using TensorFlow and EfficientNetB0
* Nutrition estimation (calories, protein, carbohydrates, and fat)
* Healthy food alternative recommendations
* AI Nutrition Assistant chatbot with preset meal guidance prompts
* Grad-CAM visualization to explain model predictions
* User authentication with secure JWT-based login and signup
* Daily meal tracking and nutrition summary dashboard
* PostgreSQL database integration for storing user meals
* REST API built with FastAPI
* React + Vite frontend
* Deployed frontend and backend for real-world usage

## AI Pipeline

1. User uploads a food image.
2. EfficientNetB0-based CNN predicts the food category.
3. Grad-CAM generates a visual explanation highlighting important regions used for prediction.
4. Nutrition information is retrieved and aggregated from multiple sources.
5. Gemini + LangChain RAG retrieves nutrition guidance from a FAISS knowledge base.
6. The assistant answers healthier-swap, next-meal, daily-intake, and protein questions.
7. User can save meals to a personal nutrition tracker.

## Tech Stack

### Machine Learning

* TensorFlow
* Keras
* EfficientNetB0
* Grad-CAM
* NumPy
* Pillow

### Backend

* FastAPI
* SQLAlchemy
* PostgreSQL
* JWT Authentication
* LangChain
* FAISS
* Gemini API
* Google/Gemini embeddings

### Frontend

* React
* Vite
* CSS

### Deployment

* Hugging Face Spaces (Backend)
* Vercel (Frontend)

## Key Highlights

* Trained on a large-scale food image dataset.
* Supports hundreds of food categories.
* Provides explainable AI using Grad-CAM.
* Includes a complete authentication and meal-tracking system.
* Designed as a production-ready full-stack AI application.
