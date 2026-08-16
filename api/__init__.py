"""FastAPI service for the Trip Planner agent (plan-v2.md WIN 9.1).

Serves the LangGraph agent over SSE, with Supabase JWT auth (no impersonation)
and Postgres conversation persistence. Entry point: ``api.main:app``.
"""
