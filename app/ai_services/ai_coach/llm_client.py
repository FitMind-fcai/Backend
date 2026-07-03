import json
import logging
import os
import re
from typing import Any, Dict, Optional

from openai import OpenAI

from app.core import config

logger = logging.getLogger(__name__)


class LLMClient:

    DEFAULT_PROVIDER       = "openrouter"
    DEFAULT_MODEL          = "qwen/qwen3-235b-a22b-2507"
    DEFAULT_TEMPERATURE    = 0.25
    DEFAULT_MAX_TOKENS     = 8000
    # GPT-4o-mini: strong medical/safety calibration, available via OpenRouter.
    # Override via AI_JUDGE_MODEL (e.g. google/gemini-flash-1.5, openai/gpt-4o).
    DEFAULT_JUDGE_MODEL      = "openai/gpt-4o-mini"
    DEFAULT_JUDGE_MAX_TOKENS = 2000
    # Context builder: same fast model as judge, small output (rules list only)
    DEFAULT_CONTEXT_BUILDER_MODEL      = "openai/gpt-4o-mini"
    DEFAULT_CONTEXT_BUILDER_MAX_TOKENS = 1200

    PROVIDER_BASE_URLS: Dict[str, str] = {
        "groq":       "https://api.groq.com/openai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "openai":     "https://api.openai.com/v1",
        "together":   "https://api.together.xyz/v1",
        "deepinfra":  "https://api.deepinfra.com/v1/openai",
        "fireworks":  "https://api.fireworks.ai/inference/v1",
    }

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.provider = (
            provider or os.getenv("AI_PROVIDER") or config.AI_PROVIDER or self.DEFAULT_PROVIDER
        ).lower()

        self.api_key = (
            api_key
            or os.getenv("AI_API_KEY")
            or config.AI_API_KEY
            or self._get_provider_api_key(self.provider)
        )
        if not self.api_key:
            raise ValueError(
                f"No API key found for provider '{self.provider}'. "
                "Set AI_API_KEY or a provider-specific key in environment."
            )

        self.base_url = (
            base_url
            or os.getenv("AI_BASE_URL")
            or config.AI_BASE_URL
            or self.PROVIDER_BASE_URLS.get(self.provider)
        )
        if not self.base_url:
            raise ValueError(f"No base URL configured for provider '{self.provider}'.")

        self.model = model or os.getenv("AI_MODEL") or config.AI_MODEL or self.DEFAULT_MODEL
        self.temperature = float(
            os.getenv("AI_COACH_TEMPERATURE")
            or str(config.AI_COACH_TEMPERATURE or self.DEFAULT_TEMPERATURE)
        )
        self.max_tokens = int(
            os.getenv("AI_COACH_MAX_TOKENS")
            or str(config.AI_COACH_MAX_TOKENS or self.DEFAULT_MAX_TOKENS)
        )
        self.rag_max_context_chars = int(os.getenv("AI_RAG_MAX_CONTEXT_CHARS", "2400"))

        self.judge_model = (
            os.getenv("AI_JUDGE_MODEL")
            or getattr(config, "AI_JUDGE_MODEL", None)
            or self.DEFAULT_JUDGE_MODEL
        )
        self.judge_max_tokens = int(
            os.getenv("AI_JUDGE_MAX_TOKENS")
            or str(getattr(config, "AI_JUDGE_MAX_TOKENS", None) or self.DEFAULT_JUDGE_MAX_TOKENS)
        )

        self.context_builder_model = (
            os.getenv("AI_CONTEXT_BUILDER_MODEL")
            or getattr(config, "AI_CONTEXT_BUILDER_MODEL", None)
            or self.DEFAULT_CONTEXT_BUILDER_MODEL
        )
        self.context_builder_max_tokens = int(
            os.getenv("AI_CONTEXT_BUILDER_MAX_TOKENS")
            or str(getattr(config, "AI_CONTEXT_BUILDER_MAX_TOKENS", None) or self.DEFAULT_CONTEXT_BUILDER_MAX_TOKENS)
        )

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=self._build_provider_headers(self.provider),
        )

        logger.info(
            "LLMClient ready — provider=%s model=%s judge_model=%s base_url=%s",
            self.provider, self.model, self.judge_model, self.base_url,
        )

    # ------------------------------------------------------------------
    # Provider setup helpers
    # ------------------------------------------------------------------

    def _get_provider_api_key(self, provider: str) -> str:
        mapping = {
            "groq":       ("GROQ_API_KEY",      getattr(config, "GROQ_API_KEY",      "")),
            "openrouter": ("OPENROUTER_API_KEY", getattr(config, "OPENROUTER_API_KEY", "")),
            "openai":     ("OPENAI_API_KEY",     getattr(config, "OPENAI_API_KEY",     "")),
            "together":   ("TOGETHER_API_KEY",   getattr(config, "TOGETHER_API_KEY",   "")),
            "deepinfra":  ("DEEPINFRA_API_KEY",  getattr(config, "DEEPINFRA_API_KEY",  "")),
            "fireworks":  ("FIREWORKS_API_KEY",  getattr(config, "FIREWORKS_API_KEY",  "")),
        }
        if provider in mapping:
            env_key, cfg_val = mapping[provider]
            return os.getenv(env_key) or cfg_val or ""
        return ""

    def _build_provider_headers(self, provider: str) -> Optional[Dict[str, str]]:
        if provider != "openrouter":
            return None
        headers: Dict[str, str] = {}
        site_url = os.getenv("OPENROUTER_SITE_URL") or getattr(config, "OPENROUTER_SITE_URL", "")
        app_name = os.getenv("OPENROUTER_APP_NAME") or getattr(config, "OPENROUTER_APP_NAME", "")
        if site_url:
            headers["HTTP-Referer"] = site_url
        if app_name:
            headers["X-Title"] = app_name
        return headers or None

    # ------------------------------------------------------------------
    # LLM call paths
    # ------------------------------------------------------------------

    def _speed_routing_kwargs(self) -> Dict[str, Any]:
        """
        OpenRouter-only: hint it to route to whichever backend provider serving
        the chosen model currently has the best throughput, instead of its
        default (price-first) provider order. Does not change the model,
        prompt, or temperature — purely a backend-selection hint, ignored by
        other providers.

        No quantization filter here: checked OpenRouter's live endpoint list
        for the configured model (qwen/qwen3-235b-a22b-2507) and every serving
        backend is fp8 (expected — a 235B-parameter model at bf16 would need
        ~470GB+ VRAM per replica). Restricting to bf16/fp16 would exclude every
        available provider and break generation outright, not just slow it down.
        """
        if self.provider != "openrouter":
            return {}
        return {"extra_body": {"provider": {"sort": "throughput"}}}

    def call_llm(self, system_prompt: str, user_prompt: str, json_mode: bool = True, model: Optional[str] = None) -> str:
        """Main generation call. Uses model override if given, else configured default."""
        call_kwargs: Dict[str, Any] = dict(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            model=model or self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=0.90,
            **self._speed_routing_kwargs(),
        )
        if json_mode:
            call_kwargs["response_format"] = {"type": "json_object"}

        completion = self._client.chat.completions.create(**call_kwargs)
        self._log_usage("generator", completion)
        return completion.choices[0].message.content

    def call_judge_llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Judge evaluation call — fast small model, near-deterministic temperature.

        The judge output is a small structured JSON, so max_tokens is capped to
        avoid wasting tokens on a large-model call for a simple evaluation task.
        """
        completion = self._client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            model=self.judge_model,
            temperature=0.1,
            max_tokens=self.judge_max_tokens,
            top_p=0.90,
            response_format={"type": "json_object"},
            **self._speed_routing_kwargs(),
        )
        self._log_usage("judge", completion)
        return completion.choices[0].message.content

    def call_context_builder_llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Context-builder call — fast model, plain-text output (rule list, not JSON).
        Runs before main generation to synthesize KB-grounded safety rules from
        targeted RAG results into a concrete, numbered rule block for Channel C.
        """
        completion = self._client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            model=self.context_builder_model,
            temperature=0.1,
            max_tokens=self.context_builder_max_tokens,
            top_p=0.90,
            **self._speed_routing_kwargs(),
        )
        self._log_usage("context_builder", completion)
        return completion.choices[0].message.content

    def _log_usage(self, label: str, completion) -> None:
        finish = completion.choices[0].finish_reason if completion.choices else None
        usage  = getattr(completion, "usage", None)
        logger.info(
            "LLM [%s] finish=%s prompt=%s completion=%s total=%s",
            label, finish,
            getattr(usage, "prompt_tokens",     None) if usage else None,
            getattr(usage, "completion_tokens", None) if usage else None,
            getattr(usage, "total_tokens",      None) if usage else None,
        )

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse an LLM response to a dict, handling:
          - Qwen3 <think>...</think> reasoning blocks emitted before the JSON
          - Markdown code fences
          - Stray text before or after the JSON object
        """
        cleaned = (response or "").strip()
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$",           "", cleaned).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Fallback: extract the first balanced top-level JSON object
        start = cleaned.find("{")
        if start != -1:
            in_string = escape = False
            depth = 0
            for idx in range(start, len(cleaned)):
                char = cleaned[idx]
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(cleaned[start: idx + 1])
                        except json.JSONDecodeError:
                            break

        raise ValueError(
            f"Could not parse LLM response as JSON "
            f"(length: {len(cleaned)} chars). Preview: {cleaned[:300]!r}"
        )

    # ------------------------------------------------------------------
    # RAG context trimming
    # ------------------------------------------------------------------

    def trim_rag_context(self, rag_context: str, context_name: str) -> str:
        context = (rag_context or "").strip()
        preview = context[:800] + ("..." if len(context) > 800 else "")
        logger.info("📚 RAG [%s] %d chars: %s", context_name, len(context), preview)
        if len(context) <= self.rag_max_context_chars:
            return context
        trimmed = context[: self.rag_max_context_chars].rstrip()
        logger.info("✂️ RAG [%s] trimmed %d → %d chars", context_name, len(context), len(trimmed))
        return trimmed
