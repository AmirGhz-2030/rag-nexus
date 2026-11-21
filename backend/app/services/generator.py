from typing import List, Dict, Any, Optional
import os
import requests
from app.core.config import settings

class RAGGenerator:
    """LLM Generator supporting Google AI Studio, LM Studio, and 9Router with Chat History."""

    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()

    def generate_response(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Build augmented prompt with context & history, then call LLM API."""
        context_str = "\n\n---\n\n".join(
            [f"[Source: {c['metadata'].get('source', 'Doc')} | Chunk #{c['metadata'].get('chunk_index', 0)}]\n{c['content']}" for c in context_chunks]
        ) if context_chunks else "No relevant context found."

        history_str = ""
        if chat_history and len(chat_history) > 0:
            formatted_history = []
            for msg in chat_history[-6:]:  # last 6 messages
                role = "User" if msg.get("role") == "user" else "Assistant"
                formatted_history.append(f"{role}: {msg.get('content', '')}")
            history_str = "\n\nPrevious Conversation:\n" + "\n".join(formatted_history)

        system_prompt = (
            "You are RAG Nexus, an intelligent research assistant. "
            "Answer the user query concisely and accurately based ONLY on the provided context below. "
            "Consider previous conversation context if relevant. "
            "If the context does not contain the answer, clearly state that you don't have enough information."
        )

        user_prompt = f"Context:\n{context_str}{history_str}\n\nUser Question:\n{query}"

        # Call selected LLM Provider
        if self.provider == "google" and settings.GOOGLE_API_KEY:
            answer = self._call_google(system_prompt, user_prompt)
        elif self.provider == "lmstudio":
            answer = self._call_lmstudio(system_prompt, user_prompt)
        elif self.provider == "9router":
            answer = self._call_9router(system_prompt, user_prompt)
        else:
            # Fallback simulator if no API key is set yet
            answer = (
                f"**[RAG Nexus Simulator — Please configure your LLM provider in ⚙️ API Settings]**\n\n"
                f"Based on the retrieved context ({len(context_chunks)} chunks found):\n\n"
                f"{context_chunks[0]['content'] if context_chunks else 'No relevant documents uploaded yet.'}"
            )

        return {
            "query": query,
            "answer": answer,
            "citations": [
                {
                    "source": c["metadata"].get("source", "Doc"),
                    "chunk_index": c["metadata"].get("chunk_index", 0),
                    "rerank_score": round(c.get("rerank_score", 0), 4)
                } for c in context_chunks
            ]
        }

    def _call_google(self, system_prompt: str, user_prompt: str) -> str:
        """Call Google AI Studio (Gemini) API."""
        try:
            from google import genai
            client = genai.Client(api_key=settings.GOOGLE_API_KEY)
            response = client.models.generate_content(
                model=settings.GOOGLE_MODEL,
                contents=f"{system_prompt}\n\n{user_prompt}"
            )
            return response.text
        except Exception as e:
            return f"Google AI Studio Error: {str(e)}"

    def _call_lmstudio(self, system_prompt: str, user_prompt: str) -> str:
        """Call LM Studio local server (OpenAI-compatible API)."""
        try:
            res = requests.post(
                f"{settings.LMSTUDIO_BASE_URL}/chat/completions",
                json={
                    "model": settings.LMSTUDIO_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "stream": False
                },
                timeout=300  # 5 minutes timeout for local hardware inference
            )
            res.raise_for_status()
            data = res.json()
            if isinstance(data, dict):
                choices = data.get("choices")
                if isinstance(choices, list) and len(choices) > 0:
                    first = choices[0]
                    if isinstance(first, dict):
                        msg = first.get("message")
                        if isinstance(msg, dict) and msg.get("content") is not None:
                            return str(msg["content"])
            return f"⚠️ Unexpected LM Studio response format: {str(data)[:300]}"
        except requests.exceptions.Timeout:
            return (
                "⏳ LM Studio Timeout: The local model took longer than 5 minutes to respond.\n\n"
                "💡 **Tips to speed up LM Studio:**\n"
                "1. Lower **Top-K Chunks** in Retrieval Controls (e.g. set Top-K to 2 or 3).\n"
                "2. Enable GPU Offloading in LM Studio settings (Nvidia/AMD CUDA/Metal acceleration).\n"
                "3. Use a smaller or quantized model in LM Studio (e.g., Llama-3.2-3B, Qwen2.5-3B-Instruct)."
            )
        except requests.exceptions.ConnectionError:
            return "❌ LM Studio Connection Error: Make sure LM Studio is running and the server is started on http://localhost:1234"
        except Exception as e:
            return f"LM Studio Error: {str(e)}"

    def _call_9router(self, system_prompt: str, user_prompt: str) -> str:
        """Call 9Router smart AI router (OpenAI-compatible API)."""
        try:
            headers = {
                "Content-Type": "application/json"
            }
            if settings.NINEROUTER_API_KEY:
                headers["Authorization"] = f"Bearer {settings.NINEROUTER_API_KEY}"

            res = requests.post(
                f"{settings.NINEROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json={
                    "model": settings.NINEROUTER_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "stream": False
                },
                timeout=120
            )
            
            # Parse JSON response if possible
            try:
                data = res.json()
            except Exception:
                res.raise_for_status()
                return res.text

            if not isinstance(data, dict):
                return f"⚠️ 9Router response is not a dictionary: {str(data)[:300]}"

            # Check if 9Router returned an error dictionary
            if "error" in data and data["error"]:
                err = data["error"]
                if isinstance(err, dict):
                    err_msg = err.get("message") or err.get("detail") or str(err)
                else:
                    err_msg = str(err)
                return f"❌ 9Router API Error: {err_msg}"

            if not res.ok:
                return f"❌ 9Router HTTP {res.status_code} Error: {res.text[:300]}"

            # Safely navigate choices -> message -> content
            choices = data.get("choices")
            if isinstance(choices, list) and len(choices) > 0:
                first = choices[0]
                if isinstance(first, dict):
                    msg = first.get("message")
                    if isinstance(msg, dict):
                        content = msg.get("content")
                        if content is not None and str(content).strip():
                            return str(content)
                        # Check reasoning content (for reasoning models)
                        reasoning = msg.get("reasoning_content") or msg.get("reasoning")
                        if reasoning and str(reasoning).strip():
                            return str(reasoning)

                    text = first.get("text")
                    if text is not None and str(text).strip():
                        return str(text)

                    finish = first.get("finish_reason")
                    if finish:
                        return f"⚠️ 9Router model finished with reason '{finish}' but returned no content."

            # Alternative fields
            if data.get("response"):
                return str(data["response"])
            if data.get("content"):
                return str(data["content"])

            return f"⚠️ 9Router returned empty or unrecognized response:\n{str(data)[:500]}"

        except requests.exceptions.ConnectionError:
            return "❌ 9Router Connection Error: Make sure 9Router is running on http://localhost:20128"
        except Exception as e:
            return f"9Router Error: {str(e)}"
