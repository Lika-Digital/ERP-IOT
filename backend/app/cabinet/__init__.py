"""Everything the ERP knows about talking to a cabinet (spec §2, §3).

One package so that the contract — paths, outcomes, payload shapes, states —
lives in one place and nothing outside it builds a cabinet URL or reads a raw
cabinet payload.
"""
