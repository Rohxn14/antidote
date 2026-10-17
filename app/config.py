# app/config.py
"""Stakes policy for the action gate.

These are configurable DEMO policy values, not universal safety rules. A real
deployment would set them per organisation, per vendor or per budget line.
"""

# Purchase orders at or above this amount (USD) always need a human approval.
AUTO_MAX_AMOUNT = 5000

# An order may proceed automatically only if it stays valid when any
# MIN_INDEPENDENT_TRUSTED_ROOTS - 1 trusted origins are quarantined, counting
# only trusted sources as roots. With 2: it must survive losing any single
# trusted origin. Sources sharing an `origin` (copies of one claim) count once.
MIN_INDEPENDENT_TRUSTED_ROOTS = 2
