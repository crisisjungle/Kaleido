class TextProcessor:
    @staticmethod
    def preprocess_text(text: str) -> str:
        return "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())

    @staticmethod
    def split_text(text: str, chunk_size: int = 500, overlap: int = 50):
        text = text or ""
        if not text:
            return []
        chunks = []
        step = max(1, chunk_size - overlap)
        for start in range(0, len(text), step):
            chunks.append(text[start:start + chunk_size])
        return chunks
