# tests/test_ui.py
"""Click through the real Streamlit app, headless."""
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


def click(at, label=None, key=None):
    buttons = [b for b in at.button if (label and b.label == label) or (key and b.key == key)]
    assert buttons, f"no button {label or key!r}; have {[b.label for b in at.button]}"
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
    click(at, "↺ Reset everything")
    assert at.session_state["graph_name"] != first
    assert [b.label for b in at.button if b.label == "Scan sources"]


def test_playground(app):
    at = app
    at.radio(key="mode").set_value("Playground").run()
    assert not at.exception, at.exception
    assert any("AND inside a reason" in i.value for i in at.info)

    click(at, key="pq_s_blog")  # AND/OR world: quarantine the blog
    assert any("Loses all support (3)" in m.value for m in at.markdown)
    click(at, "Approve repair")
    assert any("Repair applied" in s.value for s in at.success)
    click(at, key="lift_s_blog")
    assert any("Quarantine lifted" in s.value for s in at.success)

    at.selectbox(key="play_pick").set_value("3_gate").run()
    click(at, "Load into my playground")
    assert any("What the action gate lets through" in s.value for s in at.success)
    click(at, key="sub_d_po_auto")
    assert any("PO-AUTO is now authorized" in s.value for s in at.success)
