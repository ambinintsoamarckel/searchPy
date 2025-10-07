import psutil

# small helper to report process memory usage

def current_memory_mb() -> float:
    p = psutil.Process()
    return p.memory_info().rss / (1024 * 1024)
