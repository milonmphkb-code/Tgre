"""
Text processing pipeline:
  personal data filter -> word remove/replace -> line remove -> cleanup
  -> footer/hashtag -> keyword filter check -> content hash for dedup
"""
import re
import json
import hashlib

# ---------- Personal data patterns ----------
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
# International-ish phone numbers (7-15 digits, optional +, spaces/dashes)
PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\-\s]{6,14}\d)(?!\w)")
USERNAME_RE = re.compile(r"(?<!\w)@[a-zA-Z0-9_]{5,32}")
TME_LINK_RE = re.compile(r"(https?://)?t\.me/[a-zA-Z0-9_+/]+")
TG_USER_LINK_RE = re.compile(r"tg://user\?id=\d+")
# crude "personal name" heuristic is unreliable; we deliberately skip auto name-removal
# to avoid mangling normal text. Admins can use word_remove for known names instead.


def remove_personal_data(text: str) -> str:
    text = EMAIL_RE.sub("[removed]", text)
    text = TG_USER_LINK_RE.sub("[removed]", text)
    text = TME_LINK_RE.sub("[removed]", text)
    text = USERNAME_RE.sub("[removed]", text)
    text = PHONE_RE.sub("[removed]", text)
    return text


# ---------- Text editing ----------

def apply_word_remove(text: str, words: list[str]) -> str:
    for w in words:
        if not w:
            continue
        text = re.sub(re.escape(w), "", text, flags=re.IGNORECASE)
    return text


def apply_word_replace(text: str, mapping: dict[str, str]) -> str:
    for old, new in mapping.items():
        if not old:
            continue
        text = re.sub(re.escape(old), new, text, flags=re.IGNORECASE)
    return text


def apply_line_remove(text: str, substrings: list[str]) -> str:
    if not substrings:
        return text
    lines = text.split("\n")
    kept = [
        line for line in lines
        if not any(sub and sub.lower() in line.lower() for sub in substrings)
    ]
    return "\n".join(kept)


def cleanup_spacing(text: str) -> str:
    # collapse 3+ blank lines -> 1, strip trailing spaces, dedupe consecutive identical lines
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = text.split("\n")
    deduped = []
    for line in lines:
        if deduped and deduped[-1].strip() == line.strip() and line.strip() != "":
            continue
        deduped.append(line)
    return "\n".join(deduped).strip()


def add_footer_and_hashtags(text: str, footer: str, hashtags: str) -> str:
    parts = [text]
    if footer:
        parts.append(footer)
    if hashtags:
        parts.append(hashtags)
    return "\n\n".join(p for p in parts if p.strip())


# ---------- Keyword filter ----------

def passes_keyword_filter(text: str, mode: str, keywords: list[str]) -> bool:
    if mode == "none" or not keywords:
        return True
    lowered = text.lower()
    matched = any(kw.lower() in lowered for kw in keywords)
    if mode == "whitelist":
        return matched
    if mode == "blacklist":
        return not matched
    return True


# ---------- Full pipeline ----------

def process_text(raw_text: str, source_row) -> str:
    """Runs the full editing pipeline for a source's settings. Returns final text."""
    text = raw_text

    if source_row["personal_data_filter"]:
        text = remove_personal_data(text)

    word_remove = json.loads(source_row["word_remove"] or "[]")
    text = apply_word_remove(text, word_remove)

    word_replace = json.loads(source_row["word_replace"] or "{}")
    text = apply_word_replace(text, word_replace)

    line_remove = json.loads(source_row["line_remove"] or "[]")
    text = apply_line_remove(text, line_remove)

    text = cleanup_spacing(text)
    text = add_footer_and_hashtags(text, source_row["footer"], source_row["hashtags"])
    return text


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
