from typing import List, Dict

def deduplicate(results: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for r in results:
        key = (r.get('name') or '').lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
