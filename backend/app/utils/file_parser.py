import os


class FileParser:
    @staticmethod
    def extract_text(path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            try:
                import fitz
                with fitz.open(path) as doc:
                    return "\n".join(page.get_text() for page in doc)
            except Exception:
                return ""
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                with open(path, "r", encoding=encoding) as handle:
                    return handle.read()
            except UnicodeDecodeError:
                continue
            except Exception:
                return ""
        return ""
