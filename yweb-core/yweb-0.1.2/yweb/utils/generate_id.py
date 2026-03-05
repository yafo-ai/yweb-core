from uuid import uuid4
def generate_id(prefix: str = "") -> str:
    """生成一个足够复杂的ID，避免冲突。"""
    import time
    import random
    timestamp = hex(int(time.time() * 1_000_000))[2:]
    rand_part = uuid4().hex[:8]
    return f"{prefix}{timestamp}-{rand_part}"