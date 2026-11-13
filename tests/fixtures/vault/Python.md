# Python

Which file types the RAG parser handles.

- .md and .txt: read as plain text
- .pdf: pypdf, fall back to OCR for scans
- .docx: python-docx
- .html: strip tags with BeautifulSoup

Chunking: 800 tokens with 100 overlap.

## embedder.py

Embeds chunks with a local model and writes them to the vector store.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

def embed(chunks):
    return model.encode(chunks, normalize_embeddings=True)
```
