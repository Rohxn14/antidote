# app/llm.py
"""A thin LLM client for any OpenAI-compatible provider (Gemini, Groq, ...).

Configuration (environment or .env):
    LLM_API_KEY   the provider key
    LLM_MODEL     a model ID copied from the provider's console
    LLM_BASE_URL  optional; defaults to Groq's OpenAI-compatible endpoint
                  (Gemini: https://generativelanguage.googleapis.com/v1beta/openai/)

We ask for strict structured output (a JSON schema). If the provider rejects
JSON-schema mode we fall back to JSON mode with the schema in the prompt.
Callers validate the result anyway: the LLM proposes, the code checks.
"""
import json
import os
import time
from dataclasses import dataclass

GROQ_OPENAI_URL = "https://api.groq.com/openai/v1"


class LLMNotConfigured(RuntimeError):
    pass


def model_name() -> str | None:
    return os.getenv("LLM_MODEL")


def configured() -> bool:
    return bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_MODEL"))


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text


TEMPERATURE = 0


@dataclass
class Exchange:
    """One call to the model, as sent and as received (the reply verbatim)."""
    name: str                 # what was asked: extraction, inference, decision
    system: str
    user: str
    content: str              # the model's reply, exactly as the provider returned it
    model: str | None         # the model the provider says answered
    fallback: bool            # JSON-schema mode was refused; plain JSON mode was used
    usage: dict | None
    seconds: float


def call(system: str, user: str, schema: dict, name: str) -> Exchange:
    """One chat call that must return a JSON object matching `schema`."""
    if not configured():
        raise LLMNotConfigured("set LLM_API_KEY and LLM_MODEL (see .env.example)")
    from openai import BadRequestError, OpenAI  # lazy: the demo runs without a key

    client = OpenAI(api_key=os.environ["LLM_API_KEY"],
                    base_url=os.getenv("LLM_BASE_URL") or GROQ_OPENAI_URL,
                    max_retries=4, timeout=90)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    started, fallback = time.time(), False
    try:
        response = client.chat.completions.create(
            model=os.environ["LLM_MODEL"], messages=messages, temperature=TEMPERATURE,
            response_format={"type": "json_schema",
                             "json_schema": {"name": name, "schema": schema, "strict": True}})
    except BadRequestError:
        fallback = True
        messages[0]["content"] += ("\n\nReply with a single JSON object only, matching "
                                   "this JSON schema:\n" + json.dumps(schema))
        response = client.chat.completions.create(
            model=os.environ["LLM_MODEL"], messages=messages, temperature=TEMPERATURE,
            response_format={"type": "json_object"})
    usage = response.usage.model_dump() if getattr(response, "usage", None) else None
    return Exchange(name, system, user, response.choices[0].message.content or "",
                    getattr(response, "model", None), fallback, usage, time.time() - started)


def parse(content: str) -> dict:
    """The model's reply as JSON: the same parsing for live and recorded replies."""
    return json.loads(_strip_fences(content or ""))


def complete_json(system: str, user: str, schema: dict, name: str) -> dict:
    return parse(call(system, user, schema, name).content)


class Live:
    """The real model. `on_exchange` sees every call verbatim (scripts/record_run.py)."""

    def __init__(self, on_exchange=None):
        self.on_exchange = on_exchange

    @property
    def model(self) -> str | None:
        return model_name()

    def complete_json(self, system: str, user: str, schema: dict, name: str) -> dict:
        if not self.on_exchange:
            return complete_json(system, user, schema, name)
        exchange = call(system, user, schema, name)
        self.on_exchange(exchange)
        return parse(exchange.content)


LIVE = Live()


def obj(properties: dict) -> dict:
    """A strict JSON-schema object: every property required, nothing extra."""
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


STRING = {"type": "string"}
NULLABLE_STRING = {"type": ["string", "null"]}
STRINGS = {"type": "array", "items": STRING}


def described(schema: dict, text: str) -> dict:
    """A schema with a description: models read these to fill fields correctly."""
    return {**schema, "description": text}
