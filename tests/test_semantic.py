"""Tests for the optional semantic scoring layer (Phase 1).

The deterministic paths (criteria text, build gating) run with no extra deps. The
cosine/cache paths use a stub model so they don't require sentence-transformers, but
still need numpy (skipped if unavailable).
"""

import importlib.util

import pytest

from scalper.config import Profile, Weights
from scalper.models import JobPosting
from scalper.scoring import score_posting
from scalper.semantic import (
    DEFAULT_MODEL,
    SemanticScorer,
    build_semantic_scorer,
    criteria_text,
    sentence_transformers_available,
)
from scalper.store import JobStore

HAS_NUMPY = importlib.util.find_spec("numpy") is not None
needs_numpy = pytest.mark.skipif(not HAS_NUMPY, reason="numpy not installed")

if HAS_NUMPY:
    import numpy as np


def _posting(**kw):
    base = dict(
        source="test", source_id="1", url="https://x", company="Co",
        title="Backend Engineer", description="We build distributed systems in Python.",
    )
    base.update(kw)
    return JobPosting(**base)


class StubModel:
    """Deterministic bag-of-words embedder standing in for SentenceTransformer."""

    _VOCAB = ["python", "java", "backend", "engineer", "distributed", "systems",
              "sales", "marketing", "nurse", "design"]

    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True):
        vecs = []
        for t in texts:
            low = t.lower()
            v = np.array([1.0 if w in low else 0.0 for w in self._VOCAB], dtype="float32")
            if normalize_embeddings:
                n = np.linalg.norm(v)
                if n:
                    v = v / n
            vecs.append(v)
        return np.vstack(vecs)


def _stub_scorer(store=None):
    s = SemanticScorer(store=store)
    s._model = StubModel()  # bypass the lazy real-model load
    return s


# --- dependency-free paths -------------------------------------------------

def test_criteria_text_flattens_profile_intent():
    p = Profile(titles=["Backend Engineer"], required_skills=["python", "postgres"],
                nice_to_have_skills=["kafka"], keywords=["distributed systems"])
    text = criteria_text(p)
    assert "Backend Engineer" in text and "python" in text and "distributed systems" in text


def test_build_disabled_returns_none():
    assert build_semantic_scorer(enabled=False) is None


def test_build_gated_on_dependency():
    scorer = build_semantic_scorer(enabled=True)
    if sentence_transformers_available():
        assert isinstance(scorer, SemanticScorer)
    else:
        assert scorer is None


# --- cosine similarity -----------------------------------------------------

@needs_numpy
def test_identical_text_scores_near_one():
    scorer = _stub_scorer()
    profile = Profile(titles=[], required_skills=["python", "backend"], keywords=[])
    posting = _posting(title="Backend Engineer", description="python backend role")
    assert scorer(profile, posting) == pytest.approx(1.0)


@needs_numpy
def test_unrelated_text_scores_low():
    scorer = _stub_scorer()
    profile = Profile(required_skills=["python", "backend", "distributed", "systems"])
    posting = _posting(title="Sales Manager", description="marketing and sales role")
    assert scorer(profile, posting) == pytest.approx(0.0)


@needs_numpy
def test_empty_criteria_returns_none():
    scorer = _stub_scorer()
    empty = Profile(titles=[], required_skills=[], nice_to_have_skills=[], keywords=[])
    assert scorer(empty, _posting()) is None


@needs_numpy
def test_semantic_feeds_into_blended_score():
    scorer = _stub_scorer()
    profile = Profile(
        titles=[], required_skills=["python", "backend"], keywords=[],
        weights=Weights(skill_coverage=0.0, title_match=0.0, keyword=0.0, semantic=1.0),
    )
    posting = _posting(title="Backend Engineer", description="python backend")
    scored = score_posting(profile, posting, semantic_scorer=scorer)
    assert scored.breakdown.semantic == pytest.approx(1.0)
    assert scored.percent == 100


# --- store-backed cache ----------------------------------------------------

@needs_numpy
def test_embedding_cache_round_trips_and_avoids_recompute(tmp_path):
    db = tmp_path / "s.db"
    posting = _posting()
    with JobStore(db) as store:
        store.upsert_many([posting])

        scorer = _stub_scorer(store)
        scorer.prepare([posting])
        # Vector got persisted under the model name.
        cached = store.get_embeddings([posting.uid], DEFAULT_MODEL)
        assert posting.uid in cached

        # A fresh scorer loads from the store without ever touching a model.
        reloaded = SemanticScorer(store=store)  # no _model set
        reloaded.prepare([posting])
        assert posting.uid in reloaded._vecs
        # Reading the cache then scoring needs the criteria model only, so swap in
        # the stub and confirm the cached posting vector is used.
        reloaded._model = StubModel()
        assert reloaded(Profile(required_skills=["python"]), posting) is not None
