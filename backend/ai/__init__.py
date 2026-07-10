"""Agentic AI services: staffing, reporting narrative, story decomposition, C4 scaffolding.

Each service builds a prompt and calls the LLM through the factory's structured
output (never touching provider names). `LLM_PROVIDER=mock` returns deterministic,
schema-valid proposals offline (see backend/llm/mock.py).
"""
