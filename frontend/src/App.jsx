import React, { useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  Camera,
  Loader2,
  Lock,
  LogIn,
  LogOut,
  Mail,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Upload,
  User,
  Utensils,
} from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001";
const mealTypes = ["breakfast", "lunch", "dinner", "snack"];

function formatFoodName(value) {
  return value ? value.replaceAll("_", " ") : "No prediction yet";
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function numberOrNull(value) {
  return typeof value === "number" ? value : null;
}

function scaleNutritionValue(value, factor) {
  if (typeof value !== "number") return null;
  return Math.round(value * factor * 100) / 100;
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("food_auth_token") || "");
  const [currentUser, setCurrentUser] = useState(null);
  const [viewMode, setViewMode] = useState("landing"); // "landing", "login", "signup"
  const [authForm, setAuthForm] = useState({ name: "", email: "", password: "" });
  const [checkingAuth, setCheckingAuth] = useState(Boolean(token));
  const [mealDate, setMealDate] = useState(today());
  const [mealType, setMealType] = useState("lunch");
  const [portionGrams, setPortionGrams] = useState(100);
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState("");
  const [prediction, setPrediction] = useState(null);
  const [meals, setMeals] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loadingPredict, setLoadingPredict] = useState(false);
  const [savingMeal, setSavingMeal] = useState(false);
  const [loadingMeals, setLoadingMeals] = useState(false);
  const [authLoading, setAuthLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [showAlternative, setShowAlternative] = useState(false);

  const nutrition = prediction?.nutrition || {};
  const validPortionGrams = Math.max(Number(portionGrams) || 0, 0);
  const hasNutritionData = Boolean(prediction?.nutrition && nutrition.source !== "api_unavailable");
  const isPer100Gram = /100\s*g/i.test(nutrition.serving || "");
  const portionFactor = isPer100Gram ? validPortionGrams / 100 : 1;
  const scaledNutrition = {
    calories: scaleNutritionValue(nutrition.calories, portionFactor),
    protein_g: scaleNutritionValue(nutrition.protein_g, portionFactor),
    carbs_g: scaleNutritionValue(nutrition.carbs_g, portionFactor),
    fat_g: scaleNutritionValue(nutrition.fat_g, portionFactor),
  };
  const canSaveMeal = prediction && hasNutritionData && currentUser && (!isPer100Gram || validPortionGrams > 0);

  const confidencePercent = useMemo(() => {
    if (!prediction) return 0;
    return Math.round(prediction.confidence * 100);
  }, [prediction]);

  useEffect(() => {
    if (token) {
      verifySession(token);
    }
  }, []);

  useEffect(() => {
    if (currentUser && token) {
      loadMeals();
    }
  }, [mealDate, currentUser?.email, token]);

  function authHeaders(activeToken = token) {
    return { Authorization: `Bearer ${activeToken}` };
  }

  function updateAuthField(field, value) {
    setAuthForm((previous) => ({ ...previous, [field]: value }));
  }

  async function verifySession(activeToken) {
    setCheckingAuth(true);
    try {
      const response = await fetch(`${API_BASE_URL}/me`, {
        headers: authHeaders(activeToken),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Session expired.");
      setCurrentUser(data);
    } catch {
      localStorage.removeItem("food_auth_token");
      setToken("");
      setCurrentUser(null);
    } finally {
      setCheckingAuth(false);
    }
  }

  async function submitAuth(event) {
    event.preventDefault();
    setAuthLoading(true);
    setMessage("");

    const endpoint = viewMode === "signup" ? "/auth/signup" : "/auth/login";
    const payload =
      viewMode === "signup"
        ? authForm
        : { email: authForm.email, password: authForm.password };

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Authentication failed.");
      localStorage.setItem("food_auth_token", data.access_token);
      setToken(data.access_token);
      setCurrentUser(data.user);
      setAuthForm({ name: "", email: "", password: "" });
    } catch (error) {
      setMessage(error.message);
    } finally {
      setAuthLoading(false);
    }
  }

  function logout() {
    localStorage.removeItem("food_auth_token");
    setToken("");
    setCurrentUser(null);
    setMeals([]);
    setSummary(null);
    setMessage("");
    setViewMode("landing");
  }

  function selectImage(file) {
    setImageFile(file);
    setPrediction(null);
    setPortionGrams(100);
    setMessage("");
    setShowAlternative(false);
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setImagePreview(file ? URL.createObjectURL(file) : "");
  }

  async function predictImage(event) {
    event.preventDefault();
    if (!imageFile) {
      setMessage("Choose a food image first.");
      return;
    }

    setLoadingPredict(true);
    setMessage("");
    setShowAlternative(false);

    const formData = new FormData();
    formData.append("file", imageFile);

    try {
      const response = await fetch(`${API_BASE_URL}/predict`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Prediction failed.");
      setPrediction(data);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoadingPredict(false);
    }
  }

  async function loadMeals() {
    if (!currentUser || !token) return;
    setLoadingMeals(true);
    setMessage("");

    const params = new URLSearchParams({ meal_date: mealDate });

    try {
      const [mealsResponse, summaryResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/meals?${params}`, { headers: authHeaders() }),
        fetch(`${API_BASE_URL}/meals/summary?${params}`, { headers: authHeaders() }),
      ]);
      const mealsData = await mealsResponse.json();
      const summaryData = await summaryResponse.json();
      if (!mealsResponse.ok) throw new Error(mealsData.detail || "Could not load meals.");
      if (!summaryResponse.ok) throw new Error(summaryData.detail || "Could not load summary.");
      setMeals(mealsData);
      setSummary(summaryData);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoadingMeals(false);
    }
  }

  async function saveMeal() {
    if (!canSaveMeal) return;
    setSavingMeal(true);
    setMessage("");

    const payload = {
      food_name: prediction.food,
      meal_type: mealType,
      meal_date: mealDate,
      serving: isPer100Gram ? `${validPortionGrams} g` : nutrition.serving || "standard serving",
      calories: numberOrNull(scaledNutrition.calories),
      protein_g: numberOrNull(scaledNutrition.protein_g),
      carbs_g: numberOrNull(scaledNutrition.carbs_g),
      fat_g: numberOrNull(scaledNutrition.fat_g),
      confidence: prediction.confidence,
    };

    try {
      const response = await fetch(`${API_BASE_URL}/meals`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not save meal.");
      await loadMeals();
      setMessage("Meal saved to your tracker.");
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSavingMeal(false);
    }
  }

  async function deleteMeal(mealId) {
    try {
      const response = await fetch(`${API_BASE_URL}/meals/${mealId}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not delete meal.");
      await loadMeals();
    } catch (error) {
      setMessage(error.message);
    }
  }

  if (checkingAuth) {
    return (
      <main className="auth-shell">
        <Loader2 className="spin" size={30} />
      </main>
    );
  }

  if (!currentUser) {
    if (viewMode === "landing") {
      return (
        <main className="landing-shell">
          <header className="landing-header">
            <div className="landing-logo">
              <Utensils size={22} />
              <span>SmartFood AI</span>
            </div>
            <button className="secondary-btn" onClick={() => setViewMode("login")}>
              Sign In
            </button>
          </header>

          <section className="hero-section">
            <div className="badge">Your Personal Nutrition Assistant</div>
            <h1>Track your nutrition journey with AI precision</h1>
            <p className="hero-tagline">
              Log meals visually, track calorie goals effortlessly, and achieve your health objectives with instant deep learning analytics.
            </p>
            <div className="hero-ctas">
              <button className="primary-btn" onClick={() => setViewMode("signup")}>
                Get Started
              </button>
              <button className="secondary-btn" onClick={() => setViewMode("login")}>
                Sign In
              </button>
            </div>
          </section>

          <section className="features-grid">
            <div className="feature-card">
              <div className="feature-icon camera-bg">
                <Camera size={22} />
              </div>
              <h3>AI Food Detection</h3>
              <p>Upload a picture of your plate. Our trained convolutional neural network model identifies the dish instantly with high confidence.</p>
            </div>

            <div className="feature-card">
              <div className="feature-icon nutrition-bg">
                <ShieldCheck size={22} />
              </div>
              <h3>Nutrition Breakdown</h3>
              <p>Get instant calorie, protein, carbohydrate, and fat estimates scaled perfectly to your portion weight.</p>
            </div>

            <div className="feature-card">
              <div className="feature-icon tracker-bg">
                <CalendarDays size={22} />
              </div>
              <h3>Daily Tracker & Swaps</h3>
              <p>Log your meals to a visual timeline calendar, track summary metrics, and discover healthier meal alternatives.</p>
            </div>
          </section>
        </main>
      );
    }

    return (
      <main className="auth-shell">
        <form className="auth-card" onSubmit={submitAuth}>
          <div className="auth-brand">
            <ShieldCheck size={28} aria-hidden="true" />
            <div>
              <p className="eyebrow">Personal tracker</p>
              <h1>{viewMode === "signup" ? "Create Account" : "Welcome Back"}</h1>
            </div>
          </div>

          {message && <div className="notice">{message}</div>}

          {viewMode === "signup" && (
            <label className="auth-field">
              <User size={18} aria-hidden="true" />
              <input
                value={authForm.name}
                onChange={(event) => updateAuthField("name", event.target.value)}
                placeholder="Full name"
                required
              />
            </label>
          )}

          <label className="auth-field">
            <Mail size={18} aria-hidden="true" />
            <input
              type="email"
              value={authForm.email}
              onChange={(event) => updateAuthField("email", event.target.value)}
              placeholder="Email"
              required
            />
          </label>

          <label className="auth-field">
            <Lock size={18} aria-hidden="true" />
            <input
              type="password"
              value={authForm.password}
              onChange={(event) => updateAuthField("password", event.target.value)}
              placeholder="Password"
              required
              minLength={6}
            />
          </label>

          <button className="primary-btn wide-btn" type="submit" disabled={authLoading}>
            {authLoading ? <Loader2 className="spin" size={18} /> : <LogIn size={18} />}
            {viewMode === "signup" ? "Sign Up" : "Log In"}
          </button>

          <div className="auth-footer-links">
            <button
              className="link-btn"
              type="button"
              onClick={() => {
                setMessage("");
                setViewMode(viewMode === "signup" ? "login" : "signup");
              }}
            >
              {viewMode === "signup" ? "Already have an account? Log in" : "New here? Create an account"}
            </button>

            <button
              className="link-btn back-btn"
              type="button"
              onClick={() => {
                setMessage("");
                setViewMode("landing");
              }}
            >
              ← Back to Home
            </button>
          </div>
        </form>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">AI nutrition workspace</p>
          <h1>Smart Food Nutrition Analyzer</h1>
        </div>
        <div className="identity locked">
          <User size={18} aria-hidden="true" />
          <div>
            <strong>{currentUser.name}</strong>
            <span>{currentUser.email}</span>
          </div>
          <button onClick={logout} aria-label="Log out">
            <LogOut size={18} />
          </button>
        </div>
      </section>

      {message && <div className="notice">{message}</div>}

      <section className="workspace">
        <div className="predict-panel">
          <form onSubmit={predictImage} className="upload-zone">
            <label className="file-drop">
              {imagePreview ? (
                <img src={imagePreview} alt="Selected food" />
              ) : (
                <span>
                  <Upload size={34} aria-hidden="true" />
                  <strong>Upload food image</strong>
                </span>
              )}
              <input
                type="file"
                accept="image/*"
                onChange={(event) => selectImage(event.target.files?.[0] || null)}
              />
            </label>
            <button className="primary-btn" type="submit" disabled={loadingPredict}>
              {loadingPredict ? <Loader2 className="spin" size={18} /> : <Camera size={18} />}
              Analyze
            </button>
          </form>

          <div className="result-band">
            <div>
              <p className="label">Detected food</p>
              <h2>{formatFoodName(prediction?.food)}</h2>
            </div>
            <div className="confidence">
              <span>{confidencePercent}%</span>
              <small>confidence</small>
            </div>
          </div>

          {prediction?.gradcam_image && (
            <div className="explainability-grid">
              <figure>
                <img src={imagePreview} alt="Original food" />
                <figcaption>Original image</figcaption>
              </figure>
              <figure>
                <img src={prediction.gradcam_image} alt="Grad-CAM focus heatmap" />
                <figcaption>Grad-CAM focus</figcaption>
              </figure>
            </div>
          )}

          <div className="nutrition-grid">
            <Metric label="Calories" value={scaledNutrition.calories} unit="kcal" />
            <Metric label="Protein" value={scaledNutrition.protein_g} unit="g" />
            <Metric label="Carbs" value={scaledNutrition.carbs_g} unit="g" />
            <Metric label="Fat" value={scaledNutrition.fat_g} unit="g" />
          </div>

          <div className="portion-row">
            <label>
              <span>Portion eaten</span>
              <input
                type="number"
                min="1"
                max="2000"
                step="1"
                value={portionGrams}
                disabled={!isPer100Gram}
                onChange={(event) => setPortionGrams(event.target.value)}
              />
              <small>g</small>
            </label>
            <p>
              {!prediction
                ? "Upload an image to fetch nutrition data from APIs."
                : !hasNutritionData
                  ? "Nutrition data is unavailable because the configured APIs did not return a match."
                  : isPer100Gram
                    ? `Values are scaled from a ${nutrition.serving} estimate.`
                    : `Values use ${nutrition.serving || "standard serving"} estimate.`}
            </p>
          </div>

          <div className="suggestion">
            <Utensils size={18} aria-hidden="true" />
            {!prediction ? (
              <p>Analyze a food image to see a healthier swap.</p>
            ) : !showAlternative ? (
              <button
                type="button"
                className="suggestion-btn"
                onClick={() => setShowAlternative(true)}
              >
                See Healthy Alternative
              </button>
            ) : (
              <p>
                {prediction.healthy_alternative || "Healthy alternative is unavailable. Add a Gemini API key to fetch it."}
              </p>
            )}
          </div>

          <div className="save-row">
            <select value={mealType} onChange={(event) => setMealType(event.target.value)}>
              {mealTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            <button className="secondary-btn" onClick={saveMeal} disabled={!canSaveMeal || savingMeal}>
              {savingMeal ? <Loader2 className="spin" size={18} /> : <Plus size={18} />}
              Add Meal
            </button>
          </div>
        </div>

        <aside className="tracker-panel">
          <div className="tracker-header">
            <div>
              <p className="label">Daily tracker</p>
              <h2>{summary?.total_calories ?? 0} kcal</h2>
            </div>
            <button className="icon-btn" onClick={loadMeals} aria-label="Refresh meals">
              {loadingMeals ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />}
            </button>
          </div>

          <label className="date-input">
            <CalendarDays size={18} aria-hidden="true" />
            <input type="date" value={mealDate} onChange={(event) => setMealDate(event.target.value)} />
          </label>

          <div className="summary-grid">
            <Metric label="Protein" value={summary?.total_protein_g} unit="g" compact />
            <Metric label="Carbs" value={summary?.total_carbs_g} unit="g" compact />
            <Metric label="Fat" value={summary?.total_fat_g} unit="g" compact />
          </div>

          <div className="meal-list">
            {meals.length === 0 ? (
              <p className="empty-state">No meals saved for this date.</p>
            ) : (
              meals.map((meal) => (
                <div className="meal-item" key={meal.id}>
                  <div>
                    <strong>{formatFoodName(meal.food_name)}</strong>
                    <span>
                      {meal.meal_type} - {meal.serving || "serving"}
                    </span>
                  </div>
                  <div className="meal-actions">
                    <b>{meal.calories ?? 0}</b>
                    <button onClick={() => deleteMeal(meal.id)} aria-label={`Delete ${meal.food_name}`}>
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}

function Metric({ label, value, unit, compact = false }) {
  return (
    <div className={compact ? "metric compact" : "metric"}>
      <span>{label}</span>
      <strong>{value ?? "--"}</strong>
      <small>{unit}</small>
    </div>
  );
}
