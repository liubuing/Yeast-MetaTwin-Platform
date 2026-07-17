"""Versioned contracts and readiness gates for prediction plugins."""

from .schema import (
    ApplicabilityReport,
    BenchmarkReport,
    InputTransform,
    PluginInput,
    PluginResult,
    Prediction,
    RunStatus,
    UncertaintyReport,
)

SCHEMA_VERSION = "1.0.0"
RUNTIME_VERSION = "1.0.0"

__all__ = [
    "ApplicabilityReport",
    "BenchmarkReport",
    "InputTransform",
    "PluginInput",
    "PluginResult",
    "Prediction",
    "RunStatus",
    "SCHEMA_VERSION",
    "RUNTIME_VERSION",
    "UncertaintyReport",
]
