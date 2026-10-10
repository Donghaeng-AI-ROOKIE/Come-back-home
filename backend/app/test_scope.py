"""Server-owned isolation for synthetic public-app verification."""
from uuid import UUID
from app.config import settings

def synthetic_owner(owner):
    if not owner:
        return False
    try:
        normalized = str(UUID(owner))
        return normalized in {str(UUID(value.strip())) for value in settings.synthetic_guardian_ids.split(",") if value.strip()}
    except (ValueError, TypeError):
        return False

def isolated(case):
    return bool(case is not None and getattr(case, "synthetic_test", False))
