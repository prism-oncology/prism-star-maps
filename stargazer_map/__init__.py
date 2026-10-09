"""Maps of where the stargazers of a GitHub user's or organisation's repositories are."""

__version__ = "0.1.0"

from .site import build  # noqa: E402
from .stats import fetch  # noqa: E402

__all__ = ["build", "fetch"]
