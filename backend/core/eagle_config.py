"""The operator's configuration: what to look for (catalog) and where (sites).

Both are YAML files the operator writes. They are validated here into Pydantic
models; the worker syncs the sites into the database at startup, and the
catalog becomes the cached first layer of every prompt.
"""

from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_KEY_PATTERN = r"^[a-z][a-z0-9_-]*$"


class ConfigError(Exception):
    """A configuration file is missing, unreadable or invalid."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rect(_Strict):
    """A rectangle in fractions (0-1) of the frame's width and height."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _inside_frame(self) -> Rect:
        if self.x + self.w > 1 or self.y + self.h > 1:
            raise ValueError("rectangle extends beyond the frame")
        return self


class EventType(_Strict):
    """One kind of event the watchman reports."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    description: str
    counter_examples: list[str] = []
    severity: Literal["info", "warning", "critical"] = "warning"
    alert: bool = True


def _unique(keys: list[str], what: str) -> None:
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            raise ValueError(f"duplicate {what} key: {key}")
        seen.add(key)


_UNSUPPORTED_KEYWORDS = ("minLength", "maxLength")


def _check_output_schema(node: object, path: str = "extra_schema") -> None:
    """Reject what the API's structured outputs refuse, so it fails at startup, not per call."""
    if isinstance(node, list):
        for i, item in enumerate(node):
            _check_output_schema(item, f"{path}[{i}]")
        return
    if not isinstance(node, dict):
        return
    if node.get("type") == "object" and node.get("additionalProperties") is not False:
        raise ValueError(f"{path}: every object needs additionalProperties: false")
    for keyword in _UNSUPPORTED_KEYWORDS:
        if keyword in node:
            raise ValueError(f"{path}: {keyword} is not supported by structured outputs")
    for key, value in node.items():
        _check_output_schema(value, f"{path}.{key}")


class Catalog(_Strict):
    """Everything the model is told to look for."""

    instructions: str
    event_types: list[EventType] = Field(min_length=1)
    extra_schema: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _unique_keys(self) -> Catalog:
        _unique([e.key for e in self.event_types], "event type")
        if self.extra_schema is not None:
            _check_output_schema(self.extra_schema)
        return self

    def by_key(self) -> dict[str, EventType]:
        """Event types indexed by key."""
        return {e.key: e for e in self.event_types}


class CameraConfig(_Strict):
    """One camera feed."""

    key: str = Field(pattern=_KEY_PATTERN)
    label: str
    description: str = ""
    source_url: str
    crop: Rect | None = None
    ignore: list[Rect] = []
    enabled: bool = True


class SiteConfig(_Strict):
    """A group of cameras sharing context: a vessel, a building."""

    key: str = Field(pattern=_KEY_PATTERN)
    name: str
    timezone: str
    context: str = ""
    cameras: list[CameraConfig] = Field(min_length=1)

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone: {value}") from exc
        return value

    @model_validator(mode="after")
    def _unique_cameras(self) -> SiteConfig:
        _unique([c.key for c in self.cameras], "camera")
        return self


class SitesFile(_Strict):
    """The whole sites file."""

    sites: list[SiteConfig]

    @model_validator(mode="after")
    def _unique_sites(self) -> SitesFile:
        _unique([s.key for s in self.sites], "site")
        return self


def _read_yaml(path: str) -> object:
    file = Path(path)
    if not file.is_file():
        raise ConfigError(path, "file not found")
    try:
        return yaml.safe_load(file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(path, f"invalid YAML: {exc}") from exc


def _validate[T: BaseModel](model: type[T], path: str) -> T:
    try:
        return model.model_validate(_read_yaml(path))
    except ValidationError as exc:
        raise ConfigError(path, str(exc)) from exc


def load_catalog(path: str) -> Catalog:
    """Load and validate the catalog file."""
    return _validate(Catalog, path)


def load_sites(path: str) -> SitesFile:
    """Load and validate the sites file."""
    return _validate(SitesFile, path)
