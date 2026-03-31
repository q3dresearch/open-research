"""Minimal LLM wrapper via OpenRouter API."""

import json
import os
from pathlib import Path

import httpx

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "configs" / "prompts"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.1-flash-lite-preview"


def _load_env():
    """Load .env file if it exists."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _get_api_key() -> str:
    _load_env()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("Set OPENROUTER_API_KEY in .env or environment")
    return key


def load_prompt(name: str) -> str:
    """Load a prompt template from prompts/ dir."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text()


def call_llm(prompt: str, model: str = DEFAULT_MODEL, max_tokens: int = 1024) -> str:
    """Send a prompt to OpenRouter and return the text response."""
    resp = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {_get_api_key()}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def call_llm_json(prompt: str, model: str = DEFAULT_MODEL, max_tokens: int = 1024) -> dict:
    """Send a prompt and parse the response as JSON."""
    text = call_llm(prompt, model=model, max_tokens=max_tokens)
    # Extract JSON from markdown code block if present
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text.strip())
