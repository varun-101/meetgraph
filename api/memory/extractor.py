"""Action-item extractor (P3): one DeepSeek JSON-mode pass over the transcript.

Talks to DeepSeek directly via the OpenAI-compatible SDK (deepseek-chat supports
JSON mode + function calling — plan §8 D4 note). Distinct from cognify: this
produces structured rows for the action tracker; the graph gets them via the
append-only doc in pipeline.py.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from api.config import settings

log = logging.getLogger(__name__)

SYSTEM = """You extract action items from a meeting transcript.
Return STRICT JSON: {"action_items": [{"text": str, "owner_name": str|null,
"deadline": str|null}]}. `owner_name` must be one of the participant names
given, or null. `deadline` is ISO-8601 date if a date/time was stated, else null.
Only include real commitments — tasks someone agreed to do."""


async def extract_action_items(
    canonical_text: str, participant_names: list[str]
) -> list[dict[str, Any]]:
    """Returns [{"text", "owner_name", "deadline"}]. Empty list on any failure —
    extraction must never block the pipeline."""
    if not settings.llm_api_key:
        log.warning("LLM_API_KEY unset — skipping action-item extraction")
        return []
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=settings.llm_endpoint, api_key=settings.llm_api_key)
        # settings.llm_model is litellm-style ("deepseek/deepseek-chat");
        # the raw endpoint wants the bare model name.
        model = settings.llm_model.split("/")[-1]
        resp = await client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Participants: {', '.join(participant_names)}\n\n"
                        f"Transcript:\n{canonical_text[:24000]}"
                    ),
                },
            ],
            temperature=0.1,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        items = data.get("action_items", [])
        return [i for i in items if isinstance(i, dict) and i.get("text")]
    except Exception:
        log.exception("action-item extraction failed")
        return []
