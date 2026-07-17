from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


SCHEMA_VERSION = "1.0.0"


class RunStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


@dataclass(frozen=True)
class PluginInput:
    request_id: str
    capability: str
    sequence: str | None = None
    substrate_smiles: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported input schema_version: {self.schema_version}")
        if not self.request_id.strip() or not self.capability.strip():
            raise ValueError("request_id and capability are required")
        if self.sequence is not None and not self.sequence.strip():
            raise ValueError("sequence cannot be blank")
        if self.substrate_smiles is not None and not self.substrate_smiles.strip():
            raise ValueError("substrate_smiles cannot be blank")


@dataclass(frozen=True)
class InputTransform:
    field: str
    original_length: int
    effective_length: int
    truncated: bool
    strategy: str = "none"


@dataclass(frozen=True)
class ApplicabilityReport:
    assessment_status: str
    in_domain: bool | None
    ood: bool | None
    method: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.assessment_status not in {"assessed", "not_available"}:
            raise ValueError("invalid applicability assessment_status")
        if self.assessment_status == "not_available" and (self.in_domain is not None or self.ood is not None):
            raise ValueError("unavailable applicability cannot assert in-domain or OOD status")


@dataclass(frozen=True)
class UncertaintyReport:
    status: str
    method: str | None = None
    value: float | None = None
    interval: tuple[float, float] | None = None
    tree_member_count: int | None = None
    tree_member_interval_log10: tuple[float, float] | None = None
    calibrated: bool = False

    def __post_init__(self) -> None:
        if self.status not in {"available", "not_available"}:
            raise ValueError("invalid uncertainty status")
        if self.status == "not_available" and (
            self.value is not None
            or self.interval is not None
            or self.tree_member_count is not None
            or self.tree_member_interval_log10 is not None
            or self.calibrated
        ):
            raise ValueError("unavailable uncertainty cannot contain estimates")
        if (self.tree_member_count is None) != (self.tree_member_interval_log10 is None):
            raise ValueError("tree member count and interval must be reported together")
        if self.tree_member_count is not None and self.tree_member_count <= 0:
            raise ValueError("tree_member_count must be positive")


@dataclass(frozen=True)
class BenchmarkReport:
    status: str = "not_run"
    public_reference: bool = False
    dataset_name: str | None = None
    dataset_version: str | None = None
    snapshot_sha256: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"not_run", "completed"}:
            raise ValueError("invalid benchmark status")
        if self.metrics and not (
            self.status == "completed"
            and self.public_reference
            and self.dataset_name
            and self.dataset_version
            and self.snapshot_sha256
        ):
            raise ValueError("metrics require a completed, versioned public benchmark with snapshot hash")


@dataclass(frozen=True)
class Prediction:
    name: str
    value: float
    unit: str
    scale: str = "linear"


@dataclass(frozen=True)
class PluginResult:
    request_id: str
    plugin: str
    plugin_version: str
    capability: str
    status: RunStatus
    predictions: tuple[Prediction, ...] = ()
    transforms: tuple[InputTransform, ...] = ()
    applicability: ApplicabilityReport | None = None
    uncertainty: UncertaintyReport | None = None
    benchmark: BenchmarkReport = field(default_factory=BenchmarkReport)
    messages: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported output schema_version: {self.schema_version}")
        if self.status == RunStatus.READY and not self.predictions:
            raise ValueError("ready prediction results require at least one prediction")
        if self.status != RunStatus.READY and self.predictions:
            raise ValueError("blocked, unsupported, or error results cannot contain predictions")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value
