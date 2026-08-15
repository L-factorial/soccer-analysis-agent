class GeometryError(ValueError):
    """Base error for undefined or invalid spatial operations."""


class InvalidDurationError(GeometryError):
    """Raised when a calculation requires a positive duration."""


class InvalidSpeedError(GeometryError):
    """Raised when a calculation requires a positive speed."""


class UnknownPlayerError(GeometryError):
    """Raised when a player ID is not present in game state."""
