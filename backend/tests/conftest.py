import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_for_interview_arena"
os.environ["AUTH_COOKIE_SECURE"] = "true"


@pytest.fixture(autouse=True)
def reset_usage_limiter() -> None:
    try:
        from app.services.usage_limits import usage_limiter
    except Exception:
        return
    usage_limiter.reset()
    yield
    usage_limiter.reset()
