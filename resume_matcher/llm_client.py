"""Client for the local Gemma model served by LM Studio.

LM Studio exposes an OpenAI-compatible API (default http://localhost:1234/v1),
so we use the openai client pointed at the local server.
"""

from __future__ import annotations

from openai import OpenAI

from .config import Config


class LocalLLM:
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(base_url=config.llm_base_url, api_key=config.llm_api_key)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a single chat completion request and return the text reply."""
        response = self.client.chat.completions.create(
            model=self.config.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.llm_temperature,
            max_tokens=self.config.llm_max_tokens,
        )
        return response.choices[0].message.content or ""
