"""Independent magnetic QC and processing module."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "MagneticBoundary", "MagneticDataset", "MagneticDataRole", "MagneticProfile",
    "MagneticQcContext", "MagneticQcJob", "MagneticQcPipeline", "MagneticReader",
    "MagneticSurveyType", "get_profile",
]

_EXPORTS = {
    "MagneticBoundary": ("modules.magnetic.models", "MagneticBoundary"),
    "MagneticDataset": ("modules.magnetic.models", "MagneticDataset"),
    "MagneticDataRole": ("modules.magnetic.models", "MagneticDataRole"),
    "MagneticSurveyType": ("modules.magnetic.models", "MagneticSurveyType"),
    "MagneticProfile": ("modules.magnetic.magnetic_profiles", "MagneticProfile"),
    "get_profile": ("modules.magnetic.magnetic_profiles", "get_profile"),
    "MagneticQcContext": ("modules.magnetic.context", "MagneticQcContext"),
    "MagneticQcJob": ("modules.magnetic.magnetic_engine", "MagneticQcJob"),
    "MagneticQcPipeline": ("modules.magnetic.magnetic_engine", "MagneticQcPipeline"),
    "MagneticReader": ("modules.magnetic.reader", "MagneticReader"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
