from __future__ import annotations

import hashlib
import math
import re

import numpy as np

from app.core.config import get_settings


_TOKEN_RE = re.compile(r"[a-z0-9_]+", re.I)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def embed_text(text: str) -> list[float]:
    """Deterministic local embedding (hash-projection) for offline/demo use."""
    dim = get_settings().embedding_dim
    vec = np.zeros(dim, dtype=np.float64)
    tokens = tokenize(text)
    if not tokens:
        return vec.tolist()
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        vec[idx] += sign * weight
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def lexical_overlap(a: str, b: str) -> float:
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / math.sqrt(len(ta) * len(tb))
