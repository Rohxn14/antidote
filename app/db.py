# app/db.py
import os
from dotenv import load_dotenv
from falkordb import FalkorDB

# Loads .env by default; set ENV_FILE=.env.cloud to target FalkorDB Cloud instead.
load_dotenv(os.getenv("ENV_FILE", ".env"))

def get_graph(name: str | None = None):
    db = FalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        username=os.getenv("FALKORDB_USERNAME") or None,
        password=os.getenv("FALKORDB_PASSWORD") or None,
    )
    return db.select_graph(name or os.getenv("FALKORDB_GRAPH", "main"))