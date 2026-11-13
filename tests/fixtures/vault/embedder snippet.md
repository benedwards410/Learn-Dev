```python
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL = SentenceTransformer("all-MiniLM-L6-v2")


def embed(texts: list[str]) -> np.ndarray:
    return MODEL.encode(texts, normalize_embeddings=True)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b)
```
