"""The catalog and sites files load, and bad ones fail with a clear error."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.eagle_config import ConfigError, Rect, load_catalog, load_sites

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"

EVENT = {"key": "smoking", "name": "Smoking", "description": "Someone smokes."}
CAMERA = {"key": "bow", "label": "Bow", "source_url": "https://example.invalid/a.m3u8"}


def _write(tmp_path: Path, text: str) -> str:
    path = tmp_path / "file.yaml"
    path.write_text(text)
    return str(path)


def test_example_files_load():
    catalog = load_catalog(str(CONFIG_DIR / "catalog.example.yaml"))
    sites = load_sites(str(CONFIG_DIR / "sites.example.yaml"))
    keys = sorted(e.key for e in catalog.event_types)
    assert keys == ["other_vessel", "phone_use", "sleeping", "smoking"]
    assert sites.sites[0].cameras


def test_duplicate_event_key_rejected(tmp_path):
    import yaml

    text = yaml.safe_dump({"instructions": "x", "event_types": [EVENT, EVENT]})
    with pytest.raises(ConfigError, match="duplicate"):
        load_catalog(_write(tmp_path, text))


def test_duplicate_camera_key_rejected(tmp_path):
    import yaml

    site = {"key": "s", "name": "S", "timezone": "UTC", "cameras": [CAMERA, CAMERA]}
    with pytest.raises(ConfigError, match="duplicate"):
        load_sites(_write(tmp_path, yaml.safe_dump({"sites": [site]})))


def test_bad_timezone_rejected(tmp_path):
    import yaml

    site = {"key": "s", "name": "S", "timezone": "Mars/Base", "cameras": [CAMERA]}
    with pytest.raises(ConfigError, match="timezone"):
        load_sites(_write(tmp_path, yaml.safe_dump({"sites": [site]})))


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_catalog(str(tmp_path / "nope.yaml"))


def test_rect_out_of_range_rejected():
    with pytest.raises(ValidationError):
        Rect(x=0.6, y=0, w=0.5, h=0.1)


def test_extra_schema_objects_must_forbid_additional_properties():
    from core.eagle_config import Catalog

    loose = {"type": "object", "properties": {"people": {"type": "integer"}}}
    with pytest.raises(ValidationError, match="additionalProperties"):
        Catalog(instructions="x", event_types=[EVENT], extra_schema=loose)


def test_extra_schema_rejects_length_limits():
    from core.eagle_config import Catalog

    schema = {
        "type": "object",
        "properties": {"plate": {"type": "string", "maxLength": 8}},
        "required": ["plate"],
        "additionalProperties": False,
    }
    with pytest.raises(ValidationError, match="maxLength"):
        Catalog(instructions="x", event_types=[EVENT], extra_schema=schema)


def test_extra_schema_valid_is_accepted():
    from core.eagle_config import Catalog

    schema = {
        "type": "object",
        "properties": {"people": {"type": "integer"}},
        "required": ["people"],
        "additionalProperties": False,
    }
    assert Catalog(instructions="x", event_types=[EVENT], extra_schema=schema).extra_schema
