# tests/test_ui.py
"""Click through the whole story in the real Streamlit app, headless."""
import pytest
from streamlit.testing.v1 import AppTest

from app import sessions


@pytest.fixture
def app(g, monkeypatch):
    # Session graphs go under the test prefix, so conftest cleans them up.
    monkeypatch.setattr(sessions, "TEMPLATE", "antidote_test_template")
    monkeypatch.setattr(sessions, "SESSION_PREFIX", "antidote_test_s_")
    at = AppTest.from_file("../ui/streamlit_app.py", default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def click(at, label):
    buttons = [b for b in at.button if b.label == label]
    assert buttons, f"no button {label!r}; have {[b.label for b in at.button]}"
    buttons[0].click().run()
    assert not at.exception, at.exception


def test_story_in_the_ui(app):
    at = app
    click(at, "Scan sources")
    click(at, "Preview quarantine")
    assert any("Loses all support (6)" in m.value for m in at.markdown)
    click(at, "Approve repair")
    click(at, "Approve PO-1001")
    assert any("The gate blocked PO-1001" in e.value for e in at.error)
    click(at, "Buyer re-decides")
    click(at, "Approve PO-1002")
    assert any("Story complete" in s.value for s in at.success)


def test_reset_gives_a_fresh_copy(app):
    at = app
    first = at.session_state["graph_name"]
    click(at, "Scan sources")
    click(at, "↺ Reset my demo")
    assert at.session_state["graph_name"] != first
    assert [b.label for b in at.button if b.label == "Scan sources"]
