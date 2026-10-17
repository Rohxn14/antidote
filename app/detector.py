# app/detector.py
"""Rule-based detector for prompt-injection signs in source documents.

It only PROPOSES a quarantine; a human confirms it. Detection is not the
product (repair and the action gate are), so these are deliberately simple,
explainable rules rather than an LLM, which could itself be injected.
"""
import re
from dataclasses import dataclass

from app.db import ROOT
from app.schema import QUARANTINED, SOURCE

# Phrases that address an AI reader rather than a human customer.
INSTRUCTION_PHRASES = [
    "ignore previous instructions", "ignore all previous", "disregard",
    "ai assistant", "language model", "note to ai", "instructions for ai",
    "system prompt", "you must", "do not mention", "only certified",
    "do not consider", "always recommend",
]

COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
HIDDEN_ELEMENT = re.compile(
    r"<(\w+)[^>]*?(?:style\s*=\s*\"[^\"]*(?:display\s*:\s*none|visibility\s*:\s*hidden"
    r"|font-size\s*:\s*0|opacity\s*:\s*0)[^\"]*\"|\shidden[\s>])[^>]*>(.*?)</\1>",
    re.DOTALL | re.IGNORECASE)
TAG = re.compile(r"<[^>]+>")


@dataclass
class Finding:
    source_id: str
    rule: str       # html_comment, hidden_text, instruction_phrase, user_report
    evidence: str


def _clip(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _phrases(text: str) -> list[str]:
    lowered = text.lower()
    return [p for p in INSTRUCTION_PHRASES if p in lowered]


def scan_html(source_id: str, html: str) -> list[Finding]:
    findings = []
    for comment in COMMENT.findall(html):
        if _phrases(comment):
            findings.append(Finding(source_id, "html_comment", _clip(comment)))
    for _, hidden in HIDDEN_ELEMENT.findall(html):
        text = TAG.sub(" ", hidden).strip()
        if text:
            findings.append(Finding(source_id, "hidden_text", _clip(text)))
    text = TAG.sub(" ", COMMENT.sub(" ", html))  # page text, hidden parts included
    for phrase in _phrases(text):
        findings.append(Finding(source_id, "instruction_phrase", phrase))
    return findings


def scan_sources(g) -> list[Finding]:
    """Scan every non-quarantined source whose uri is a local file."""
    rows = g.ro_query(f"MATCH (s:{SOURCE}) WHERE s.trust <> $q RETURN s.id, s.uri ORDER BY s.id",
                      {"q": QUARANTINED}).result_set
    findings = []
    for source_id, uri in rows:
        path = ROOT / uri if uri else None
        if path and path.is_file():
            findings.extend(scan_html(source_id, path.read_text(encoding="utf-8")))
    return findings


def report(source_id: str, reason: str) -> Finding:
    """A human reports a source by hand; it follows the same preview path."""
    return Finding(source_id, "user_report", _clip(reason))
