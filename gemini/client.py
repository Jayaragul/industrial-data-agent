from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class GeminiResult:
    text: str
    token_usage: dict[str, Any]


class GeminiClient:
    def __init__(self) -> None:
        self._load_env_file()
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.model = os.getenv("GEMINI_MODEL", "")
        self.temperature = float(os.getenv("GEMINI_TEMPERATURE", "0") or 0)
        self.thinking_budget = int(os.getenv("GEMINI_THINKING_BUDGET", "2048") or 2048)
        self._client = None
        self.last_error: str | None = None
        if os.getenv("GEMINI_DISABLE_LIVE") == "1":
            self.last_error = "Live Gemini calls are disabled by GEMINI_DISABLE_LIVE=1."
        elif not self.api_key or not self.model:
            missing = []
            if not self.api_key:
                missing.append("GEMINI_API_KEY")
            if not self.model:
                missing.append("GEMINI_MODEL")
            self.last_error = "Missing Gemini configuration: " + ", ".join(missing) + "."
        else:
            try:
                from google import genai

                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                self.last_error = f"Gemini client initialization failed: {exc}"
                self._client = None

    @property
    def connected(self) -> bool:
        return self._client is not None and bool(self.model)

    def generate_text(self, prompt: str, *, thinking_budget: int | None = None, json_output: bool = False) -> GeminiResult:
        self.last_error = None
        if not self.connected:
            self.last_error = "Gemini is not configured or connected."
            return GeminiResult(text="", token_usage={"mode": "offline_fallback"})
        last_error = ""
        for _ in range(2):
            try:
                from google.genai import types
                config = types.GenerateContentConfig(
                    temperature=self.temperature,
                    thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget or self.thinking_budget),
                    response_mime_type="application/json" if json_output else None,
                )
                response = self._client.models.generate_content(model=self.model, contents=prompt, config=config)
                break
            except Exception as exc:
                last_error = str(exc)
        else:
            self.last_error = last_error or "Gemini did not return a response."
            return GeminiResult(text="", token_usage={"mode": "live_request_failed_after_retry", "error": last_error})
        usage = getattr(response, "usage_metadata", None)
        text = getattr(response, "text", "") or ""
        if not text.strip():
            self.last_error = "Gemini returned an empty response."
        return GeminiResult(text=text, token_usage={"usage_metadata": str(usage)})

    def generate_json(self, prompt: str, *, thinking_budget: int | None = None) -> dict[str, Any] | None:
        result = self.generate_text(prompt, thinking_budget=thinking_budget, json_output=True)
        if not result.text:
            if not self.last_error:
                self.last_error = "Gemini returned no JSON response."
            return None
        text = result.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
            text = text.rsplit("```", 1)[0].strip()
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                return payload
            self.last_error = "Gemini returned valid JSON, but not an object."
            return None
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                self.last_error = "Gemini returned non-JSON text when JSON was required."
                return None
            try:
                payload = json.loads(text[start:end + 1])
                if isinstance(payload, dict):
                    return payload
                self.last_error = "Gemini returned valid JSON, but not an object."
                return None
            except json.JSONDecodeError:
                self.last_error = "Gemini returned malformed JSON."
                return None

    def _load_env_file(self) -> None:
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if not env_path.exists():
            return
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
