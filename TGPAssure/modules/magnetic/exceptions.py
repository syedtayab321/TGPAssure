from __future__ import annotations


class MagneticError(Exception):
    """Base error for the magnetic module."""


class MagneticReadError(MagneticError):
    """Raised when a magnetic source file cannot be parsed safely."""


class MagneticSchemaError(MagneticReadError):
    """Raised when required magnetic columns are absent or ambiguous."""


class MagneticProcessingError(MagneticError):
    """Raised when a requested processing operation is invalid."""


class MagneticRepositoryError(MagneticError):
    """Raised when magnetic persistence fails."""
