import asyncio
import json
import os
import re
from typing import Any

import httpx
from loguru import logger

from src.config import LLM_API_URL, LLM_MODEL
from src.http_client import get_async_client

_LOCAL_LLM: Any = None  # (model, tokenizer)


def _remote_generate(
    messages: list[dict[str, str]],
    max_new_tokens: int = 1024,
    temperature: float = 0.6,
    top_p: float = 0.95,
) -> str:
    """Generate text via remote chat completions API (OpenAI-compatible)."""
    response = httpx.post(
        f"{LLM_API_URL}/chat/completions",
        json={
            "model": LLM_MODEL,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": temperature,
            "top_p": top_p,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    msg = data["choices"][0]["message"]
    content = msg.get("content", "")
    # Qwen 3.5 puts output in reasoning_content when content is empty
    if not content.strip() and msg.get("reasoning_content"):
        content = msg["reasoning_content"]
    # Strip thinking section and special tokens
    content = re.sub(r'<\|im_end\|>|<\|im_start\|>|</?think>', '', content)
    return content.strip()


async def _remote_generate_async(
    messages: list[dict[str, str]],
    max_new_tokens: int = 1024,
    temperature: float = 0.6,
    top_p: float = 0.95,
) -> str:
    """Generate text via remote chat completions API (async, pooled client)."""
    response = await get_async_client().post(
        f"{LLM_API_URL}/chat/completions",
        json={
            "model": LLM_MODEL,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": temperature,
            "top_p": top_p,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    msg = data["choices"][0]["message"]
    content = msg.get("content", "")
    # Qwen 3.5 puts output in reasoning_content when content is empty
    if not content.strip() and msg.get("reasoning_content"):
        content = msg["reasoning_content"]
    # Strip thinking section and special tokens
    content = re.sub(r'<\|im_end\|>|<\|im_start\|>|</?think>', '', content)
    return content.strip()


def _get_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def _load_model() -> tuple[Any, Any]:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    path = os.path.expanduser(os.getenv("LLM_MODEL_PATH", ""))
    if not path:
        raise RuntimeError("LLM_MODEL_PATH not set")

    logger.info(f"Loading LLM from {path}...")
    device = _get_device()
    logger.info(f"Using device: {device}")

    tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True)

    kwargs = {
        "trust_remote_code": True,
        "torch_dtype": "auto",
    }
    if device == "cuda":
        kwargs["device_map"] = "auto"
        # required for response_format json_object
        kwargs["attn_implementation"] = "eager"

    model = AutoModelForCausalLM.from_pretrained(path, **kwargs)
    if device == "cpu":
        model = model.to(device)

    logger.success(f"LLM loaded ({sum(p.numel() for p in model.parameters()) / 1e9:.1f}B params)")
    return model, tokenizer


def _get_model() -> tuple[Any, Any]:
    global _LOCAL_LLM
    if _LOCAL_LLM is None:
        _LOCAL_LLM = _load_model()
    return _LOCAL_LLM


def generate(
    messages: list[dict[str, str]],
    max_new_tokens: int = 1024,
    temperature: float = 0.6,
    top_p: float = 0.95,
) -> str:
    """Generate text from a list of messages (role: user/assistant/system)."""
    if LLM_API_URL:
        return _remote_generate(messages, max_new_tokens, temperature, top_p)

    model, tokenizer = _get_model()

    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    outputs = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_p=top_p,
        do_sample=True,
        pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
    )

    response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=False)
    # Strip thinking section and special tokens
    response = re.sub(r'<\|im_end\|>|<\|im_start\|>|</?think>', '', response)
    return response.strip()


async def generate_async(
    messages: list[dict[str, str]],
    max_new_tokens: int = 1024,
    temperature: float = 0.6,
    top_p: float = 0.95,
) -> str:
    """Async variant of generate: remote API via pooled client, local model in thread."""
    if LLM_API_URL:
        return await _remote_generate_async(messages, max_new_tokens, temperature, top_p)
    return await asyncio.to_thread(generate, messages, max_new_tokens, temperature, top_p)


def _parse_json(text: str) -> dict:
    """Extract JSON object from model output."""
    # Strip thinking tags if present
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

    # Try finding ```json block first
    for marker in ["```json", "```"]:
        if marker in text:
            parts = text.split(marker)
            if len(parts) >= 2:
                candidate = parts[1].strip()
                if candidate.endswith("```"):
                    candidate = candidate[:-3].strip()
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass

    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end+1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot parse JSON from: {text[:200]}")


def _build_rag_messages(query: str, context: list[dict[str, str]], top_k: int = 5) -> list[dict[str, str]]:
    docs = context[:top_k]
    context_text = "\n\n".join(
        f"[{i+1}] {d.get('title', 'Untitled')}\n{d.get('abstract', '')[:2000]}"
        for i, d in enumerate(docs)
    )

    system_prompt = (
        "Ты — ассистент по научным статьям. "
        "Отвечай ТОЛЬКО JSON, без пояснений, без рассуждений. "
        "Формат: {\"answer\": \"...\", \"sources\": [1, 2], \"confidence\": \"high|medium|low\"}. "
        "Используй только информацию из статей. "
        "sources — номера источников из контекста [1], [2] и т.д. "
        "Если ответа нет — confidence: low."
    )

    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Контекст:\n{context_text}\n\nВопрос: {query}",
        },
    ]


def _finalize_rag_answer(raw: str) -> dict:
    try:
        return _parse_json(raw)
    except ValueError as e:
        logger.error(f"Structured output failed: {e}")
        return {
            "answer": raw[:500],
            "sources": [],
            "confidence": "low",
            "_parse_error": str(e),
        }


def generate_rag_answer(
    query: str, context: list[dict[str, str]], top_k: int = 5
) -> dict:
    """Generate structured answer from search results.

    Returns dict with: answer, sources (list), confidence (str).
    """
    messages = _build_rag_messages(query, context, top_k)
    max_ask_tokens = int(os.getenv("LLM_MAX_ASK_TOKENS", "1024"))
    raw = generate(messages, max_new_tokens=max_ask_tokens)
    return _finalize_rag_answer(raw)


async def generate_rag_answer_async(
    query: str, context: list[dict[str, str]], top_k: int = 5
) -> dict:
    """Async variant of generate_rag_answer."""
    messages = _build_rag_messages(query, context, top_k)
    max_ask_tokens = int(os.getenv("LLM_MAX_ASK_TOKENS", "1024"))
    raw = await generate_async(messages, max_new_tokens=max_ask_tokens)
    return _finalize_rag_answer(raw)


def extract_entities(text: str) -> dict:
    """Extract methods, datasets, tasks from paper abstract.

    Returns dict with: methods, datasets, tasks, models.
    """
    system_prompt = (
        "Извлеки сущности из текста статьи. "
        "Ответь ТОЛЬКО JSON, без пояснений. "
        "Формат: {\"methods\": [...], \"datasets\": [...], \"tasks\": [...], \"models\": [...]}. "
        "Если сущностей нет — пустой массив."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Текст:\n{text[:3000]}"},
    ]

    raw = generate(messages, max_new_tokens=512)
    try:
        return _parse_json(raw)
    except ValueError as e:
        logger.warning(f"Entity extraction parse failed: {e}")
        return {"methods": [], "datasets": [], "tasks": [], "models": [], "_raw": raw[:300]}


# ─── Reranker ────────────────────────────────────────────────────────────────

_RERANKER: Any = None  # JinaForRanking model


def _get_reranker_path() -> str:
    path = os.path.expanduser(os.getenv("RERANKER_MODEL_PATH", ""))
    if not path:
        raise RuntimeError("RERANKER_MODEL_PATH not set")
    return path


def _load_reranker() -> Any:
    from transformers import AutoModel

    path = _get_reranker_path()
    logger.info(f"Loading reranker from {path}...")
    device = _get_device()
    logger.info(f"Reranker device: {device}")

    model = AutoModel.from_pretrained(
        path,
        trust_remote_code=True,
        torch_dtype="auto",
        device_map="auto" if device == "cuda" else None,
    ).eval()
    if device == "cpu":
        model = model.to(device)

    logger.success(f"Reranker loaded ({sum(p.numel() for p in model.parameters()) / 1e9:.1f}B params)")
    return model


def _get_reranker() -> Any:
    global _RERANKER
    if _RERANKER is None:
        _RERANKER = _load_reranker()
    return _RERANKER


def preload() -> None:
    """Preload all models (LLM + reranker) into memory. Skips if remote API or path not set."""
    if LLM_API_URL:
        logger.info(f"Remote LLM configured: {LLM_MODEL} @ {LLM_API_URL}")
    elif os.getenv("LLM_MODEL_PATH"):
        _get_model()
    if os.getenv("RERANKER_MODEL_PATH"):
        _get_reranker()


def rerank(
    query: str,
    documents: list[dict[str, str]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Rerank documents via Jina Reranker v3 (cosine similarity scoring).

    Args:
        query: Search query.
        documents: List of dicts with 'id', 'title', 'abstract'.
        top_k: Number of top documents to return.

    Returns:
        Same documents sorted by relevance score descending, with 'score' added.
        If RERANKER_MODEL_PATH unset, returns first top_k unchanged.
    """
    if not os.getenv("RERANKER_MODEL_PATH"):
        logger.debug("RERANKER_MODEL_PATH unset — skipping rerank")
        return list(documents[:top_k])

    model = _get_reranker()

    # Build text list: title + abstract for each doc
    doc_strings = [f"{d.get('title', '')}\n{d.get('abstract', '')[:2000]}" for d in documents]

    # Use model's built-in rerank
    results = model.rerank(query, doc_strings, top_n=top_k)

    # Map back to original documents by index
    index_to_doc = {i: d for i, d in enumerate(documents)}
    return [
        {**index_to_doc[r["index"]], "score": round(float(r["relevance_score"]), 4)}
        for r in results
    ]
