# scripts/keepalive.py
"""Touch the FalkorDB Cloud instance so the free tier does not stop it for
being idle during judging. Run by .github/workflows/keepalive.yml.

    python -m scripts.keepalive
"""
from app import sessions
from app.db import get_db


def main() -> None:
    db = get_db()
    graphs = db.list_graphs()
    if sessions.TEMPLATE in graphs:
        n = db.select_graph(sessions.TEMPLATE).ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
        print(f"template {sessions.TEMPLATE}: {n} nodes")
    else:
        print(f"template missing; graphs: {graphs} (the app re-seeds it on its next start)")


if __name__ == "__main__":
    main()
