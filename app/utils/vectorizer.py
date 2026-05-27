import math
import re

class HashVectorizer:
    def __init__(self, dim: int = 128) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", text.lower())
        if not tokens:
            return vec
        for tok in tokens:
            idx = hash(tok) % self.dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b))
