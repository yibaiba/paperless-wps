import json
from hashlib import sha256


def digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return sha256(encoded).hexdigest()
