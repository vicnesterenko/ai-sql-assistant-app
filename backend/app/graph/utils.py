import re

MUTATION_VERB_TO_SQL_KEYWORD = {
    r"\bdelete\b": "DELETE",
    r"\bremove\b": "DELETE",
    r"\bdrop\b": "DROP",
    r"\btruncate\b": "TRUNCATE",
    r"\binsert\b": "INSERT",
    r"\bupdate\b": "UPDATE",
    r"\balter\b": "ALTER",
    r"\bgrant\b": "GRANT",
    r"\brevoke\b": "REVOKE",
}

def detect_mutation_keyword(*texts: str) -> str | None:
    combined = " ".join(t for t in texts if t).lower()
    for pattern, keyword in MUTATION_VERB_TO_SQL_KEYWORD.items():
        if re.search(pattern, combined):
            return keyword
    return None

def obj_value(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
