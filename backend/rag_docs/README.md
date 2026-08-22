# Nutrition RAG Documents

Add nutrition reference PDFs, Markdown, or text files in this folder.

The nutrition assistant will:

- load files from `backend/rag_docs/`
- split them into chunks
- embed them with `gemini-embedding-001`
- store them in FAISS at runtime
- pass retrieved context to Gemini when answering chat questions

If this folder is empty, the assistant still answers with Gemini using the detected food,
nutrition estimate, and meal tracker context.
