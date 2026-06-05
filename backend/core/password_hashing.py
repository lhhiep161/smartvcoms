import base64
import hashlib
import secrets


ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
SALT_BYTES = 32
HASH_BYTES = 32


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty base64url value")
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def make_password_hash(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    password_text = str(password or "")
    rounds = int(iterations)
    if rounds <= 0:
        raise ValueError("iterations must be positive")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password_text.encode("utf-8"), salt, rounds, dklen=HASH_BYTES)
    return f"{ALGORITHM}${rounds}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        password_text = str(password or "")
        raw = str(stored_hash or "").strip()
        algorithm, iterations_text, salt_text, hash_text = raw.split("$", 3)
        if algorithm != ALGORITHM:
            return False
        rounds = int(iterations_text)
        if rounds <= 0:
            return False
        salt = _b64url_decode(salt_text)
        expected_digest = _b64url_decode(hash_text)
        computed_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password_text.encode("utf-8"),
            salt,
            rounds,
            dklen=len(expected_digest),
        )
        return secrets.compare_digest(computed_digest, expected_digest)
    except Exception:
        return False
