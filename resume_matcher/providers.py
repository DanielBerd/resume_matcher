"""Presets for the GUI's Server tab.

Every entry speaks the OpenAI-compatible API, so switching between them is
only a matter of base URL, key, and model id. The hosted model ids are
starting points that the user can change; providers rename models often.
"""

from __future__ import annotations

from dataclasses import dataclass

LOCAL = "local"
HOSTED = "hosted"


@dataclass(frozen=True)
class Provider:
    name: str
    mode: str
    base_url: str
    model: str
    # Whether the key field matters. Local servers ignore it.
    needs_key: bool


PROVIDERS: tuple[Provider, ...] = (
    Provider("Unsloth Desktop", LOCAL, "http://localhost:8888/v1", "gemma-4-12b", False),
    Provider("Local (other OpenAI-compatible)", LOCAL, "http://localhost:8000/v1", "", False),
    Provider("OpenAI", HOSTED, "https://api.openai.com/v1", "gpt-4o-mini", True),
    Provider("OpenRouter", HOSTED, "https://openrouter.ai/api/v1", "google/gemma-3-27b-it", True),
    Provider("Groq", HOSTED, "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", True),
    Provider("Custom (OpenAI-compatible)", HOSTED, "", "", True),
)

BY_NAME = {p.name: p for p in PROVIDERS}


def pick_default_model(models: list[str], preferred: str) -> str:
    """Pick the model to preselect: the first whose id contains the preferred
    name (case-insensitive), else the first model. Server-side ids carry org
    prefixes and quantization suffixes that we do not want to hardcode."""
    needle = preferred.lower()
    for model in models:
        if needle and needle in model.lower():
            return model
    return models[0]


def provider_names() -> list[str]:
    return [p.name for p in PROVIDERS]


def find(name: str) -> Provider | None:
    return BY_NAME.get(name)
