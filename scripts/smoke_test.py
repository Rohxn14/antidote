# scripts/smoke_test.py
from app.db import get_graph
g = get_graph("smoke")
g.query("MERGE (n:Ping {id: 1}) SET n.at = timestamp()")
print(g.ro_query("MATCH (n:Ping) RETURN n.id, n.at").result_set)