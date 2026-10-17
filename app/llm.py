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


def complete_json(system: str, user: str, schema: dict, name: str) -> dict:
    """One chat call that must return a JSON object matching `schema`."""
    if not configured():
        raise LLMNotConfigured("set LLM_API_KEY and LLM_MODEL (see .env.example)")
    from openai import BadRequestError, OpenAI  # lazy: the demo runs without a key

    client = OpenAI(api_key=os.environ["LLM_API_KEY"],
                    base_url=os.getenv("LLM_BASE_URL") or GROQ_OPENAI_URL,
                    max_retries=4, timeout=90)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        response = client.chat.completions.create(
            model=os.environ["LLM_MODEL"], messages=messages, temperature=0,
            response_format={"type": "json_schema",
                             "json_schema": {"name": name, "schema": schema, "strict": True}})
    except BadRequestError:
        messages[0]["content"] += ("\n\nReply with a single JSON object only, matching "
                                   "this JSON schema:\n" + json.dumps(schema))
        response = client.chat.completions.create(
            model=os.environ["LLM_MODEL"], messages=messages, temperature=0,
            response_format={"type": "json_object"})
    return json.loads(_strip_fences(response.choices[0].message.content or ""))


def obj(properties: dict) -> dict:
    """A strict JSON-schema object: every property required, nothing extra."""
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


STRING = {"type": "string"}
NULLABLE_STRING = {"type": ["string", "null"]}
STRINGS = {"type": "array", "items": STRING}
