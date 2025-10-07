import re

# Very small french-friendly soundex-like helper for demonstration
def simple_phonetic(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub('[^a-z0-9]', '', s)
    # compress vowels
    s = re.sub('[aeiouy]+', 'a', s)
    # collapse consonant runs
    s = re.sub('(ss|tt|ll|pp|rr)', lambda m: m.group(1)[0], s)
    return s[:8]
