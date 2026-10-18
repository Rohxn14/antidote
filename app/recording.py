# app/recording.py
"""A real model run, saved verbatim and replayed through the same agent code.

scripts/record_run.py runs the real agents (an LLM on Groq) through the demo story
and saves every exchange: the prompts sent and the model's reply exactly as the
provider returned it, plus a provenance file (model, provider, date, code version,
prompt hashes, temperature, file hash, attempt number).

Replaying it, the agents' own code runs as in a live run: it builds the prompts from
the same documents and the same memory, and instead of calling the provider it gets
the recorded reply to that exact prompt, parsed by the same code (llm.parse) and
checked by the same checks. A prompt the recording does not contain is never given an
invented answer: the step reports that it was not recorded.
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from app import llm
from app.db import ROOT

DIR = ROOT / "data" / "recordings"
EXCHANGES, PROVENANCE = "exchanges.jsonl", "provenance.json"


class NotRecorded(RuntimeError):
    """The recorded run never asked the model this exact question."""


def key(name: str, system: str, user: str) -> str:
    return hashlib.sha256("\0".join((name, system, user)).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Recording:
    def __init__(self, folder: Path):
        self.folder = folder
        self.provenance = json.loads((folder / PROVENANCE).read_text(encoding="utf-8"))
        self.exchanges = [json.loads(line) for line in
                          (folder / EXCHANGES).read_text(encoding="utf-8").splitlines() if line.strip()]
        self.replies = {e["key"]: e for e in self.exchanges}

    @property
    def model(self) -> str:
        return self.provenance["model"]

    def complete_json(self, system: str, user: str, schema: dict, name: str) -> dict:
        exchange = self.replies.get(key(name, system, user))
        if exchange is None:
            covered = "; ".join(self.provenance.get("paths", {}).values())
            raise NotRecorded(
                f"The recorded {self.model} run never reached this step, so there is no real "
                f"answer to replay (it covers: {covered}). Run Antidote locally with Live AI to "
                "see what the model does here.")
        return llm.parse(exchange["content"])

    def intact(self) -> bool:
        """The exchanges file is the one the provenance file describes."""
        return sha256_file(self.folder / EXCHANGES) == self.provenance["exchanges_sha256"]

    def info(self) -> dict:
        p = self.provenance
        return {"model": p["model"], "provider": p["provider"], "recorded_at": p["recorded_at"],
                "attempt": p["attempt"], "calls": len(self.exchanges),
                "exchanges_sha256": p["exchanges_sha256"]}


@lru_cache(maxsize=1)
def default() -> Recording | None:
    """The newest recorded run, or None if there is none."""
    folders = sorted((f for f in DIR.glob("*") if (f / PROVENANCE).is_file()),
                     key=lambda f: json.loads((f / PROVENANCE).read_text(encoding="utf-8"))["recorded_at"])
    return Recording(folders[-1]) if folders else None
