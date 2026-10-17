# scripts/without_falkordb.py
"""Print what each capability does with FalkorDB, and what happens without it.

    python -m scripts.without_falkordb
"""
import sys

from app import centrality


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    for label, with_falkordb in (("WITH FalkorDB", True), ("WITHOUT FalkorDB", False)):
        print(f"\n== {label}")
        for r in centrality.run(with_falkordb):
            mark = "OK " if r["ok"] else "FAIL"
            print(f"  [{mark}] {r['capability']} ({r['feature']}): "
                  f"{r['result'] if r['ok'] else r['error']}  [{r['ms']} ms, "
                  f"{len(r['statements'])} statements]")


if __name__ == "__main__":
    main()
