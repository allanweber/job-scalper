"""Service layer for the multi-tenant Job Scalper backend.

Phase 2 building blocks (transport-agnostic, so they're unit-testable without
FastAPI): envelope encryption for BYO keys, hot settings, repositories, Google
sign-in + JWT/refresh auth, and the quota engine. Phase 3 wires these into the
FastAPI app. See docs/DESIGN.md and ADRs 0008-0011.
"""
