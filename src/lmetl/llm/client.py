"""OpenAI-compatible LLM client for Ollama / vLLM / OpenAI."""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import openai

logger = logging.getLogger(__name__)

# Inference parameters that can be passed via extra_body to OpenAI-compatible APIs
_EXTRA_BODY_PARAMS = frozenset({
    "top_k", "min_p", "repeat_penalty", "num_predict",
})

# Parameters supported as direct kwargs to chat.completions.create
_DIRECT_PARAMS = frozenset({
    "temperature", "top_p",
})


@dataclass
class ExtractionResponse:
    """Response from an LLM extraction call with metadata."""

    content: str
    token_usage_input: int
    token_usage_output: int
    latency_ms: int
    model_name: str
    model_endpoint: str


class LLMClient:
    """OpenAI-compatible client that works with Ollama, vLLM, and OpenAI."""

    def __init__(self, llm_config: Dict[str, Any]):
        """Initialize from the lmetl.llm config dict.

        Args:
            llm_config: The 'llm' section from lmetl YAML config.
        """
        self.endpoint = llm_config.get("endpoint", "http://192.168.9.160:11434")
        self.model = llm_config.get("model", "gpt-oss:120b")
        self.timeout = llm_config.get("timeout", 300)
        self.max_retries = llm_config.get("max_retries", 3)
        self.parameters = llm_config.get("parameters", {})

        self.client = openai.OpenAI(
            base_url=f"{self.endpoint}/v1",
            api_key="ollama",
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

    def extract(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[dict] = None,
    ) -> ExtractionResponse:
        """Send extraction request and return structured response with metadata."""
        start_time = time.time()

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        # Direct OpenAI params
        for key in _DIRECT_PARAMS:
            if key in self.parameters:
                kwargs[key] = self.parameters[key]

        # Ollama/vLLM extra params via extra_body
        extra_body: Dict[str, Any] = {}
        for key in _EXTRA_BODY_PARAMS:
            if key in self.parameters:
                extra_body[key] = self.parameters[key]
        if extra_body:
            kwargs["extra_body"] = extra_body

        if response_format:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        latency_ms = int((time.time() - start_time) * 1000)

        usage = response.usage
        token_input = usage.prompt_tokens if usage else 0
        token_output = usage.completion_tokens if usage else 0
        content = response.choices[0].message.content or ""

        logger.info(
            "LLM call: model=%s, tokens_in=%d, tokens_out=%d, latency=%dms",
            self.model,
            token_input,
            token_output,
            latency_ms,
        )

        return ExtractionResponse(
            content=content,
            token_usage_input=token_input,
            token_usage_output=token_output,
            latency_ms=latency_ms,
            model_name=self.model,
            model_endpoint=self.endpoint,
        )
