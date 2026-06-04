import os
from pathlib import Path


APP_ENV_PATH = Path(__file__).resolve().parents[2] / "package_config" / "app.env"


def load_app_env() -> None:
    if not APP_ENV_PATH.exists():
        return
    try:
        for raw_line in APP_ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip()
    except Exception:
        return
