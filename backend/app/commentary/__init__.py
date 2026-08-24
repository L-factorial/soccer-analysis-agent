"""Optional, post-planning commentary integration.

Deleting this package and the single call in the analyze endpoint completely
removes the prototype without changing planning, simulation, or scheduling.
"""

from app.commentary.service import generate_commentary

__all__ = ["generate_commentary"]
