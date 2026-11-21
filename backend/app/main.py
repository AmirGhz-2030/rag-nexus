import os
import sys
import time

# Ensure backend directory is in sys.path when running script directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import pathlib

from app.core.config import settings
from app.services.document_loader import DocumentProcessor
from app.services.retriever import HybridRetriever
from app.services.generator import RAGGenerator

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Advanced Modular RAG Engine with Hybrid Search & Cross-Encoder Reranking | Developed by AmirGhz-2030 (https://github.com/AmirGhz-2030)"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Services
document_processor = DocumentProcessor()
retriever = HybridRetriever()
generator = RAGGenerator()

class QueryRequest(BaseModel):
    query: str
    top_k: Optional[int] = 4
    alpha: Optional[float] = 0.5
    chat_history: Optional[List[Dict[str, str]]] = None

class SettingsRequest(BaseModel):
    llm_provider: Optional[str] = None
    google_api_key: Optional[str] = None
    google_model: Optional[str] = None
    lmstudio_base_url: Optional[str] = None
    lmstudio_model: Optional[str] = None
    ninerouter_base_url: Optional[str] = None
    ninerouter_api_key: Optional[str] = None
    ninerouter_model: Optional[str] = None

@app.get("/api/v1/health")
def health_check():
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "indexed_chunks_count": len(retriever.documents_store),
        "indexed_files": retriever.get_indexed_files(),
        "llm_provider": settings.LLM_PROVIDER
    }

@app.get("/api/v1/documents")
def list_documents():
    """List all currently indexed documents."""
    return {
        "total_chunks": len(retriever.documents_store),
        "files": retriever.get_indexed_files()
    }

@app.post("/api/v1/clear-index")
def clear_index():
    """Clear all indexed documents from memory."""
    retriever.clear_documents()
    return {
        "status": "success",
        "message": "Index cleared successfully.",
        "indexed_chunks_count": 0
    }

@app.post("/api/v1/ingest")
async def ingest_documents(files: List[UploadFile] = File(...)):
    """Upload and index one or multiple documents (PDF, TXT, MD)."""
    try:
        results = []
        last_ext = 'txt'
        for file in files:
            content = await file.read()
            text = document_processor.extract_text(content, file.filename)
            if not text.strip():
                continue

            chunks = document_processor.create_chunks(text, file.filename)
            retriever.add_documents(chunks)
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'txt'
            last_ext = ext
            results.append({
                "filename": file.filename,
                "chunks": len(chunks)
            })

        if not results:
            raise HTTPException(status_code=400, detail="No readable text found in uploaded files.")

        total_chunks = len(retriever.documents_store)

        if last_ext == 'pdf':
            recommended_top_k = min(6, max(3, total_chunks // 2))
            recommended_alpha = 0.6
        elif last_ext == 'md':
            recommended_top_k = min(5, max(2, total_chunks // 2))
            recommended_alpha = 0.4
        else:
            recommended_top_k = min(4, max(2, total_chunks // 2))
            recommended_alpha = 0.5

        return {
            "status": "success",
            "files_processed": results,
            "total_files": len(results),
            "file_type": last_ext,
            "total_indexed_chunks": total_chunks,
            "recommended_top_k": recommended_top_k,
            "recommended_alpha": recommended_alpha
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest documents: {str(e)}")

@app.post("/api/v1/query")
def query_rag(request: QueryRequest):
    """Execute Hybrid Retrieval and LLM Generation."""
    try:
        start_time = time.time()
        
        # 1. Hybrid Search + Reranking
        retrieved_chunks = retriever.search(
            query=request.query,
            top_k=request.top_k,
            alpha=request.alpha
        )

        # 2. LLM Generation (with chat history if provided)
        result = generator.generate_response(
            query=request.query,
            context_chunks=retrieved_chunks,
            chat_history=request.chat_history
        )
        
        latency = round(time.time() - start_time, 3)

        return {
            "query": request.query,
            "answer": result["answer"],
            "citations": result["citations"],
            "chunks": retrieved_chunks,
            "latency_seconds": latency
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing error: {str(e)}")

# --- Settings Endpoints ---

def _find_env_file() -> str:
    """Find the .env file path (project root or backend root)."""
    project_root = pathlib.Path(__file__).resolve().parent.parent.parent
    env_path = project_root / ".env"
    if not env_path.exists():
        # Create from example if available
        for candidate in ("env.example", ".env.example"):
            example = project_root / candidate
            if example.exists():
                env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
                break
        else:
            env_path.write_text("", encoding="utf-8")
    return str(env_path)


def _update_env_file(key: str, value: str):
    """Update a single key in the .env file."""
    env_path = _find_env_file()
    lines = pathlib.Path(env_path).read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    pathlib.Path(env_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.get("/api/v1/settings")
def get_settings():
    """Return current LLM settings (keys are masked)."""
    def mask(key: str) -> str:
        if not key or key.startswith("your_"):
            return ""
        if len(key) <= 8:
            return "****"
        return key[:4] + "*" * (len(key) - 8) + key[-4:]

    return {
        "llm_provider": settings.LLM_PROVIDER,
        "google_api_key": mask(settings.GOOGLE_API_KEY),
        "google_model": settings.GOOGLE_MODEL,
        "lmstudio_base_url": settings.LMSTUDIO_BASE_URL,
        "lmstudio_model": settings.LMSTUDIO_MODEL,
        "ninerouter_base_url": settings.NINEROUTER_BASE_URL,
        "ninerouter_api_key": mask(settings.NINEROUTER_API_KEY),
        "ninerouter_model": settings.NINEROUTER_MODEL,
    }


@app.post("/api/v1/settings")
def update_settings(req: SettingsRequest):
    """Update LLM provider and API keys at runtime and persist to .env."""
    updated_fields = []

    if req.llm_provider is not None:
        settings.LLM_PROVIDER = req.llm_provider.lower()
        generator.provider = settings.LLM_PROVIDER
        _update_env_file("LLM_PROVIDER", settings.LLM_PROVIDER)
        updated_fields.append("llm_provider")

    active_provider = settings.LLM_PROVIDER.lower()

    if active_provider == "google":
        if req.google_api_key is not None and req.google_api_key.strip():
            settings.GOOGLE_API_KEY = req.google_api_key.strip()
            _update_env_file("GOOGLE_API_KEY", settings.GOOGLE_API_KEY)
            updated_fields.append("google_api_key")

        if req.google_model is not None and req.google_model.strip():
            settings.GOOGLE_MODEL = req.google_model.strip()
            _update_env_file("GOOGLE_MODEL", settings.GOOGLE_MODEL)
            updated_fields.append("google_model")

    elif active_provider == "lmstudio":
        if req.lmstudio_base_url is not None and req.lmstudio_base_url.strip():
            settings.LMSTUDIO_BASE_URL = req.lmstudio_base_url.strip()
            _update_env_file("LMSTUDIO_BASE_URL", settings.LMSTUDIO_BASE_URL)
            updated_fields.append("lmstudio_base_url")

        if req.lmstudio_model is not None and req.lmstudio_model.strip():
            settings.LMSTUDIO_MODEL = req.lmstudio_model.strip()
            _update_env_file("LMSTUDIO_MODEL", settings.LMSTUDIO_MODEL)
            updated_fields.append("lmstudio_model")

    elif active_provider == "9router":
        if req.ninerouter_base_url is not None and req.ninerouter_base_url.strip():
            settings.NINEROUTER_BASE_URL = req.ninerouter_base_url.strip()
            _update_env_file("NINEROUTER_BASE_URL", settings.NINEROUTER_BASE_URL)
            updated_fields.append("ninerouter_base_url")

        if req.ninerouter_api_key is not None and req.ninerouter_api_key.strip():
            settings.NINEROUTER_API_KEY = req.ninerouter_api_key.strip()
            _update_env_file("NINEROUTER_API_KEY", settings.NINEROUTER_API_KEY)
            updated_fields.append("ninerouter_api_key")

        if req.ninerouter_model is not None and req.ninerouter_model.strip():
            val = req.ninerouter_model.strip()
            if val.startswith("http://") or val.startswith("https://") or "localhost:" in val:
                raise HTTPException(status_code=400, detail="Invalid Model Name: You pasted a URL into the Model field. Please enter your 9Router model/combo name (e.g. 'hermes_test').")
            settings.NINEROUTER_MODEL = val
            _update_env_file("NINEROUTER_MODEL", settings.NINEROUTER_MODEL)
            updated_fields.append("ninerouter_model")

    return {
        "status": "success",
        "updated_fields": updated_fields,
        "active_provider": settings.LLM_PROVIDER
    }

@app.post("/api/v1/test-connection")
def test_connection():
    """Test the current LLM provider connection with a minimal request."""
    import requests as req_lib
    provider = settings.LLM_PROVIDER.lower()
    start = time.time()

    try:
        if provider == "google":
            if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY.startswith("your_"):
                return {"status": "error", "provider": provider, "message": "❌ Google API Key is not set. Get one from https://aistudio.google.com/apikey"}
            from google import genai
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            response = client.models.generate_content(
                model=settings.GOOGLE_MODEL,
                contents="Say OK"
            )
            answer = response.text
            elapsed = round(time.time() - start, 2)
            return {"status": "ok", "provider": provider, "model": settings.GOOGLE_MODEL, "message": f"✅ Connected! Response: {answer[:50]}...", "latency": elapsed}

        elif provider == "lmstudio":
            # Test by hitting the models endpoint
            try:
                r = req_lib.get(f"{settings.LMSTUDIO_BASE_URL}/models", timeout=5)
                r.raise_for_status()
                models = r.json().get("data", [])
                model_names = [m.get("id", "unknown") for m in models[:5]]
                elapsed = round(time.time() - start, 2)
                return {"status": "ok", "provider": provider, "model": settings.LMSTUDIO_MODEL, "message": f"✅ Connected! Available models: {', '.join(model_names)}", "latency": elapsed}
            except req_lib.exceptions.ConnectionError:
                return {"status": "error", "provider": provider, "message": f"❌ Cannot connect to LM Studio at {settings.LMSTUDIO_BASE_URL}. Make sure LM Studio is running and the server is started."}

        elif provider == "9router":
            if not settings.NINEROUTER_API_KEY:
                return {"status": "error", "provider": provider, "message": "❌ 9Router API Key is not set. Copy it from 9Router dashboard (http://localhost:20128/dashboard)"}
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {settings.NINEROUTER_API_KEY}"}
            try:
                r = req_lib.post(
                    f"{settings.NINEROUTER_BASE_URL}/chat/completions",
                    headers=headers,
                    json={
                        "model": settings.NINEROUTER_MODEL,
                        "messages": [{"role": "user", "content": "Say OK"}],
                        "max_tokens": 10,
                        "stream": False
                    },
                    timeout=30
                )
                if r.status_code == 401:
                    return {"status": "error", "provider": provider, "message": "❌ Invalid API Key. Check your 9Router dashboard."}
                if r.status_code == 404:
                    return {"status": "error", "provider": provider, "message": f"❌ Model '{settings.NINEROUTER_MODEL}' not found. Check the model name in 9Router."}
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict) and data.get("error"):
                    err = data["error"]
                    err_str = err.get("message") if isinstance(err, dict) else str(err)
                    return {"status": "error", "provider": provider, "message": f"❌ 9Router API Error: {err_str}"}

                answer = "Connected (OK)"
                if isinstance(data, dict):
                    choices = data.get("choices")
                    if isinstance(choices, list) and len(choices) > 0 and isinstance(choices[0], dict):
                        msg = choices[0].get("message")
                        if isinstance(msg, dict) and msg.get("content"):
                            answer = str(msg["content"])
                elapsed = round(time.time() - start, 2)
                return {"status": "ok", "provider": provider, "model": settings.NINEROUTER_MODEL, "message": f"✅ Connected! Response: {answer[:50]}", "latency": elapsed}
            except req_lib.exceptions.ConnectionError:
                return {"status": "error", "provider": provider, "message": f"❌ Cannot connect to 9Router at {settings.NINEROUTER_BASE_URL}. Make sure 9Router is running."}
            except Exception as e:
                return {"status": "error", "provider": provider, "message": f"❌ 9Router Error: {str(e)}"}

        else:
            return {"status": "error", "provider": provider, "message": f"❌ Unknown provider: {provider}"}

    except Exception as e:
        return {"status": "error", "provider": provider, "message": f"❌ Connection test failed: {str(e)}"}


# Serve Frontend static files if directory exists
frontend_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
)

if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
