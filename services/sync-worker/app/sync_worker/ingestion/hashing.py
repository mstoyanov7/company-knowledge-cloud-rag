import hashlib


def compute_content_hash(content_text: str) -> str:
    normalized = content_text.strip().replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
