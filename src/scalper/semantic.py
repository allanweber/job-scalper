"""Optional semantic similarity component for Stage 1 scoring (ADR 0003, Phase 1).

The deterministic components (skill coverage, title, keyword) only fire on literal
keyword hits. This adds a `semantic` component: embed the profile's criteria text and
each posting's `search_text` with a local sentence-transformers model, and score them
by cosine similarity in [0,1]. It catches relevant roles that don't contain the exact
skill words, at zero marginal cost (everything runs locally).

Posting embeddings are cached in the store keyed by `uid` + model name, so only
new/changed postings are recomputed and reports stay fast. The whole layer is optional:
if `sentence-transformers` isn't installed (the `[semantic]` extra), `build_semantic_scorer`
returns ``None`` and `score_all` falls back to the deterministic blend, with the semantic
weight renormalizing out (existing behavior).
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

from scalper.config import Profile
from scalper.models import JobPosting

if TYPE_CHECKING:  # avoid importing the store (and pulling its deps) at module load
    from scalper.store import JobStore

#: Small, fast, CPU-friendly default. `bge-small-en-v1.5` is a quality alternative.
DEFAULT_MODEL = "all-MiniLM-L6-v2"


def sentence_transformers_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


def criteria_text(profile: Profile) -> str:
    """Flatten a profile's intent (titles + skills + keywords) into one string."""
    parts = [
        *profile.titles,
        *profile.required_skills,
        *profile.nice_to_have_skills,
        *profile.keywords,
    ]
    return ", ".join(p.strip() for p in parts if p.strip())


class SemanticScorer:
    """Callable `(profile, posting) -> float | None` matching the `SemanticScorer` hook.

    Heavy work (model load, encoding) is lazy and cached. Call `prepare(postings)`
    once before scoring to batch-embed cache misses; `__call__` then reads the cache.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, store: "JobStore | None" = None):
        self.model_name = model_name
        self._store = store
        self._model = None  # lazily loaded SentenceTransformer
        self._vecs: dict[str, object] = {}  # uid -> np.ndarray (posting embeddings)
        self._criteria_vecs: dict[str, object] = {}  # criteria text -> np.ndarray

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _encode(self, texts: list[str]):
        """Encode to L2-normalized float32 vectors (so dot product == cosine)."""
        vecs = self.model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return vecs.astype("float32")

    def prepare(self, postings: list[JobPosting]) -> None:
        """Load cached embeddings from the store and compute any that are missing."""
        import numpy as np

        uids = [p.uid for p in postings]
        if self._store is not None:
            for uid, blob in self._store.get_embeddings(uids, self.model_name).items():
                self._vecs[uid] = np.frombuffer(blob, dtype="float32")

        missing = [p for p in postings if p.uid not in self._vecs]
        if not missing:
            return

        vecs = self._encode([p.search_text for p in missing])
        fresh: list[tuple[str, bytes]] = []
        for posting, vec in zip(missing, vecs):
            self._vecs[posting.uid] = vec
            fresh.append((posting.uid, vec.tobytes()))
        if self._store is not None:
            self._store.put_embeddings(self.model_name, fresh)

    def _posting_vec(self, posting: JobPosting):
        vec = self._vecs.get(posting.uid)
        if vec is None:  # prepare() wasn't called for this posting; encode on demand
            vec = self._encode([posting.search_text])[0]
            self._vecs[posting.uid] = vec
        return vec

    def _criteria_vec(self, text: str):
        vec = self._criteria_vecs.get(text)
        if vec is None:
            vec = self._encode([text])[0]
            self._criteria_vecs[text] = vec
        return vec

    def __call__(self, profile: Profile, posting: JobPosting) -> float | None:
        import numpy as np

        text = criteria_text(profile)
        if not text or not posting.search_text.strip():
            return None
        sim = float(np.dot(self._criteria_vec(text), self._posting_vec(posting)))
        # Cosine is in [-1, 1]; clamp to the [0, 1] the breakdown expects.
        return max(0.0, min(1.0, sim))


def build_semantic_scorer(
    store: "JobStore | None" = None,
    model_name: str = DEFAULT_MODEL,
    enabled: bool = True,
) -> SemanticScorer | None:
    """Return a scorer, or ``None`` if disabled or the optional dep is missing."""
    if not enabled or not sentence_transformers_available():
        return None
    return SemanticScorer(model_name=model_name, store=store)
