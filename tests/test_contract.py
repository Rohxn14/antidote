# tests/test_contract.py
"""api/contract.py (Pydantic) and web/src/contract.ts (TypeScript) must agree:
the same event types, and the same models with the same fields."""
import inspect
import re

from pydantic import BaseModel

from api import contract
from app.db import ROOT

TS = (ROOT / "web" / "src" / "contract.ts").read_text(encoding="utf-8")


def ts_interfaces() -> dict[str, set[str]]:
    found = {}
    for name, body in re.findall(r"export interface (\w+) \{(.*?)\n\}", TS, re.DOTALL):
        found[name] = set(re.findall(r"^\s+(\w+)\??:", body, re.MULTILINE))
    return found


def python_models() -> dict[str, set[str]]:
    """Every data, request and response model (envelopes are checked separately)."""
    return {name: set(cls.model_fields)
            for name, cls in inspect.getmembers(contract, inspect.isclass)
            if issubclass(cls, BaseModel) and cls is not BaseModel
            and cls.__module__ == contract.__name__ and not name.endswith("Event")}


def test_every_model_has_a_typescript_interface_with_the_same_fields():
    ts = ts_interfaces()
    for name, fields in python_models().items():
        assert name in ts, f"{name} is missing from web/src/contract.ts"
        assert ts[name] == fields, f"{name}: python {sorted(fields)} != ts {sorted(ts[name])}"


def test_no_typescript_interface_without_a_python_model():
    assert set(ts_interfaces()) - {"Envelope"} <= set(python_models())


def test_event_types_agree():
    ts_types = re.search(r"EVENT_TYPES = \[(.*?)\] as const", TS, re.DOTALL).group(1)
    assert re.findall(r'"(\w+)"', ts_types) == contract.EVENT_TYPES
    envelopes = [cls for name, cls in inspect.getmembers(contract, inspect.isclass)
                 if name.endswith("Event") and issubclass(cls, BaseModel)]
    assert sorted(cls.model_fields["type"].default for cls in envelopes) == \
        sorted(contract.EVENT_TYPES)


def test_events_round_trip_as_ndjson_lines():
    from pydantic import TypeAdapter
    adapter = TypeAdapter(contract.Event)
    event = contract.FactRecordedEvent(seq=3, data=contract.FactRecordedData(
        fact_id="b_x", text="Acme is certified", vendor_id=None, document_id="s_doc",
        quote="Acme is certified.", supported=True))
    line = event.model_dump_json()
    assert "\n" not in line
    assert adapter.validate_json(line) == event
