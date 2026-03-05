"""Content rating hierarchy and access control helpers."""

RATING_ORDER = {"G": 0, "PG": 1, "PG-13": 2, "R": 3, "NC-17": 4, "XXX": 5}


def allowed_ratings(max_rating: str) -> list[str]:
    """Return all ratings at or below max_rating."""
    ceiling = RATING_ORDER.get(max_rating, 1)
    return [r for r, level in RATING_ORDER.items() if level <= ceiling]


def can_access(user_max: str, project_rating: str) -> bool:
    """Check if a user with max_rating can view a project with project_rating."""
    return RATING_ORDER.get(user_max, 1) >= RATING_ORDER.get(project_rating, 3)
