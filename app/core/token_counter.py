import re
from typing import Optional

_enc = None

def get_tokenizer():
    global _enc
    if _enc is None:
        try:
            import tiktoken
            _enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _enc = False
    return _enc

def count_tokens(text: Optional[str]) -> int:
    """
    Calculates exact token count using OpenAI's official cl100k_base tokenizer.
    If offline or library unavailable, falls back to standard LLM token estimation formula.
    """
    if not text:
        return 0
    
    tokenizer = get_tokenizer()
    if tokenizer:
        try:
            return len(tokenizer.encode(text))
        except Exception:
            pass

    # Robust Fallback Token Estimation:
    # 1 token is approximately 3.8 - 4 characters for English / Mixed alphanumeric
    # Words + punctuation weighting
    words = len(re.findall(r'\w+|[^\w\s]', text, re.UNICODE))
    char_count = len(text)
    return max(1, int((char_count / 3.8 + words * 0.4) / 2))
