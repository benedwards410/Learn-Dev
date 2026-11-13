# File types for parsing

Which file types the RAG parser handles.

- .md and .txt: read as plain text
- .pdf: pypdf, fall back to OCR for scans
- .docx: python-docx
- .html: strip tags with BeautifulSoup

Chunking: 800 tokens with 100 overlap.
