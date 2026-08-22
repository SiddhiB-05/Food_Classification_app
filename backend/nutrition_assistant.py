import os
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv(Path(__file__).resolve().parent / ".env")

try:
    from langchain_community.vectorstores import FAISS
    from langchain_community.document_loaders import PyPDFLoader, TextLoader
    from langchain_core.documents import Document
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False


DEFAULT_CHAT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_EMBEDDING_MODEL = "text-embedding-004"
MAX_CONTEXT_DOCS = 4
RAG_DOCS_DIR = Path(__file__).resolve().parent / "rag_docs"

_vector_store = None
_vector_error = None


class NutritionFacts(BaseModel):
    serving: str | None = None
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    source: str | None = None


class NutritionChatRequest(BaseModel):
    food_name: str | None = Field(default=None, max_length=120)
    confidence: float | None = Field(default=None, ge=0, le=1)
    nutrition: NutritionFacts = Field(default_factory=NutritionFacts)
    question: str = Field(..., min_length=2, max_length=600)
    intent: str | None = Field(default=None, max_length=80)
    meal_date: date = Field(default_factory=date.today)


class NutritionChatResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)
    rag_enabled: bool = False
    answer_source: str = "gemini"


SYSTEM_PROMPT = """
You are an AI Nutrition Assistant inside a food image classifier app.
The app may pass a detected food name and nutrition estimate from an uploaded image.
It always passes the user's meal tracker data for the selected date.
The user may ask in any language. Internally translate the user's question to English,
reason in English, then answer naturally in the user's language/style unless they ask
for another language.
Do not use food-specific hardcoded rules. Use the detected food name if available and
the meal tracker context you receive. If no detected food is available, answer from the
meal tracker context only and do not ask the user to upload an image unless image analysis
is specifically needed.
If the user asks for a healthier alternative, generate it for the detected food when
available, otherwise suggest based on the saved meals.
If the user asks what they ate today, list the logged meals cleanly (e.g. "• Snack: Kachori (290 kcal)"), then give totals only if useful.
If retrieved RAG context is present, use it as supporting context. If no RAG context is
present, still answer from Gemini using the detected food and meal tracker context.
If the user's message is only a greeting or small talk, reply briefly and do not analyze
the detected food unless the user asks a nutrition or meal question.
Give concise, practical nutrition guidance in 90 words or fewer unless the user asks
for a full list or detailed analysis.
Do not diagnose disease, prescribe treatment, or claim exact nutrition values.
When values are estimates, say so plainly.
Prefer clear food suggestions that are realistic for an Indian user when relevant.
""".strip()


def _get_google_api_key():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    placeholder_values = {"your_actual_key", "your_gemini_api_key", "replace_me"}
    if api_key.strip().lower() in placeholder_values:
        return None
    return api_key.strip()


def _format_food_name(food_name):
    if not food_name:
        return "No current food image"
    return food_name.replace("_", " ").strip().title()


def _format_number(value):
    if value is None:
        return "unknown"
    rounded = round(float(value), 1)
    if rounded.is_integer():
        return str(int(rounded))
    return str(rounded)


def _nutrition_context(nutrition):
    return (
        f"Serving: {nutrition.serving or 'unknown'}; "
        f"calories: {_format_number(nutrition.calories)} kcal; "
        f"protein: {_format_number(nutrition.protein_g)} g; "
        f"carbs: {_format_number(nutrition.carbs_g)} g; "
        f"fat: {_format_number(nutrition.fat_g)} g; "
        f"source: {nutrition.source or 'unknown'}."
    )


def _summary_context(summary):
    if not summary:
        return "No daily meal summary is available."

    return (
        f"Date: {summary.get('date', 'today')}; "
        f"total calories: {_format_number(summary.get('total_calories'))} kcal; "
        f"protein: {_format_number(summary.get('total_protein_g'))} g; "
        f"carbs: {_format_number(summary.get('total_carbs_g'))} g; "
        f"fat: {_format_number(summary.get('total_fat_g'))} g."
    )


def _get_attr(item, key):
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _meals_context(meals):
    if not meals:
        return "No meals logged for this date."

    rows = []
    for meal in meals[:8]:
        rows.append(
            (
                f"{_get_attr(meal, 'meal_type')}: {_format_food_name(_get_attr(meal, 'food_name') or 'food')} "
                f"({_format_number(_get_attr(meal, 'calories'))} kcal, "
                f"{_format_number(_get_attr(meal, 'protein_g'))} g protein)"
            )
        )
    return "\n".join(rows)


def _load_rag_documents():
    if not RAG_DOCS_DIR.exists():
        return []

    documents = []
    for path in RAG_DOCS_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.name.lower() == "readme.md":
            continue

        suffix = path.suffix.lower()
        try:
            if suffix == ".pdf":
                documents.extend(PyPDFLoader(str(path)).load())
            elif suffix in {".txt", ".md"}:
                documents.extend(TextLoader(str(path), encoding="utf-8").load())
        except Exception:
            continue

    if not documents:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=120,
    )
    return splitter.split_documents(documents)


def _build_vector_store():
    global _vector_store, _vector_error

    if _vector_store is not None:
        return _vector_store
    if _vector_error:
        return None
    if not LANGCHAIN_AVAILABLE:
        _vector_error = "LangChain, FAISS, or Google GenAI packages are not installed."
        return None

    api_key = _get_google_api_key()
    if not api_key:
        _vector_error = "GEMINI_API_KEY or GOOGLE_API_KEY is not configured."
        return None

    try:
        documents = _load_rag_documents()
        if not documents:
            _vector_error = f"No RAG documents found in {RAG_DOCS_DIR}."
            return None

        embeddings = GoogleGenerativeAIEmbeddings(
            model=os.getenv("GEMINI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
            google_api_key=api_key,
        )
        _vector_store = FAISS.from_documents(documents, embeddings)
        return _vector_store
    except Exception as exc:
        _vector_error = str(exc)
        return None


def _retrieve_context(request):
    vector_store = _build_vector_store()
    if vector_store is None:
        return []

    query = " ".join(
        [
            request.food_name or "",
            request.intent or "",
            request.question,
            _nutrition_context(request.nutrition),
        ]
    )

    try:
        return vector_store.similarity_search(query, k=MAX_CONTEXT_DOCS)
    except Exception:
        return []


CHAT_FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
]


def _chat_models():
    primary = os.getenv("GEMINI_CHAT_MODEL") or os.getenv("GEMINI_MODEL") or DEFAULT_CHAT_MODEL
    models = [primary]
    for model in CHAT_FALLBACK_MODELS:
        if model not in models:
            models.append(model)
    return models


def _llm_response(request, summary, meals):
    if not LANGCHAIN_AVAILABLE or not _get_google_api_key():
        return None

    documents = _retrieve_context(request)

    sources = []
    for document in documents:
        source = document.metadata.get("source")
        if source and source not in sources:
            sources.append(source)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            (
                "human",
                (
                    "Detected food: {food_name}\n"
                    "Model confidence: {confidence}\n"
                    "Nutrition estimate: {nutrition}\n\n"
                    "Daily summary: {summary}\n"
                    "Logged meals:\n{meals}\n\n"
                    "Retrieved RAG context:\n{context}\n\n"
                    "Response style: {response_style}\n"
                    "User request: {question}"
                ),
            ),
        ]
    )

    invoke_payload = {
        "food_name": (
            _format_food_name(request.food_name)
            if request.food_name
            else "No current image prediction; answer from meal tracker data."
        ),
        "confidence": (
            f"{round(request.confidence * 100)}%" if request.confidence is not None else "unknown"
        ),
        "nutrition": _nutrition_context(request.nutrition),
        "summary": _summary_context(summary),
        "meals": _meals_context(meals),
        "context": (
            "\n".join(document.page_content for document in documents)
            if documents
            else "No RAG document context was retrieved. Answer from Gemini using the detected food and meal tracker context."
        ),
        "response_style": "Answer naturally in the same language and style as the user's request.",
        "question": request.question,
    }

    for model_name in _chat_models():
        try:
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=_get_google_api_key(),
                temperature=0.35,
                max_output_tokens=250,
            )
            response = (prompt | llm).invoke(invoke_payload)

            raw_content = getattr(response, "content", response)
            if isinstance(raw_content, list):
                text_parts = []
                for part in raw_content:
                    if isinstance(part, str):
                        text_parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
                    elif hasattr(part, "text"):
                        text_parts.append(getattr(part, "text", ""))
                answer = " ".join(text_parts).strip()
            elif isinstance(raw_content, str):
                answer = raw_content.strip()
            else:
                answer = str(raw_content).strip()

            if answer:
                return NutritionChatResponse(
                    answer=answer,
                    sources=sources or ["gemini"],
                    rag_enabled=bool(documents),
                    answer_source="gemini_rag" if documents else "gemini",
                )
        except Exception:
            continue

    return None


def _gemini_unavailable_response():
    return (
        "Gemini is unavailable right now, so I cannot reliably understand or answer this chat request. "
        "Please check GEMINI_API_KEY, network access, and the backend logs, then try again."
    )


def generate_nutrition_chat(request, summary: dict[str, Any] | None, meals):
    q_clean = (request.question or "").strip().lower()
    greetings = {"heyy", "hey", "hi", "hello", "hi there", "hey there", "good morning", "good evening", "namaste"}
    if q_clean in greetings or q_clean.rstrip("!?.") in greetings:
        food_hint = f" I see you scanned **{_format_food_name(request.food_name)}**!" if request.food_name else ""
        return NutritionChatResponse(
            answer=f"Hey there! How can I help you with your nutrition or meal tracker today?{food_hint}",
            sources=["instant_greeting"],
            rag_enabled=False,
            answer_source="gemini",
        )

    response = _llm_response(request, summary, meals)
    if response is not None:
        return response

    return NutritionChatResponse(
        answer=_gemini_unavailable_response(),
        sources=["gemini_unavailable"],
        rag_enabled=False,
        answer_source="unavailable",
    )
