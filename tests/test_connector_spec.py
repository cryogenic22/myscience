"""ConnectorSpec — the file-based connector primitive (DataHub "Connector Press").

A connector is a plain YAML spec file (connectors/specs/<source_id>.yaml) governed
by connectors/specs/SCHEMA.md. These DB-free, HTTP-free tests pin load / lint /
round-trip and — the keystone — the dynamic loader that turns a spec into one of
the EXISTING generic connectors (Rest/Csv/Rss), so a runtime-registered source
flows through the same IntegrationPipeline as every bespoke connector with no new
connector class.
"""
from __future__ import annotations

import textwrap

import pytest


REST_SPEC_YAML = textwrap.dedent(
    """
    source_id: demo_rest
    source_name: Demo REST Source
    connector_type: API_REST
    record_type: drug
    trust_tier: 2
    must_capture: [generic_name]
    license: CC-BY-4.0
    cadence: {hour: "*/12"}
    config:
      url: https://example.com/api/drugs
      external_id_field: id
      records_path: data.results
      field_map: {generic_name: name}
      identifiers_map: {generic_name: generic_name}
      text_field: description
      pagination: page
    """
)


def test_load_and_roundtrip():
    from connectors.spec import ConnectorSpec

    spec = ConnectorSpec.from_yaml(REST_SPEC_YAML)
    assert spec.source_id == "demo_rest"
    assert spec.connector_type == "API_REST"
    assert spec.record_type == "drug"
    assert spec.trust_tier == 2
    assert spec.must_capture == ["generic_name"]
    assert spec.config["url"].startswith("https://")
    # round-trip through dict is stable
    assert ConnectorSpec.from_dict(spec.to_dict()).to_dict() == spec.to_dict()
    # and through YAML
    assert ConnectorSpec.from_yaml(spec.to_yaml()).to_dict() == spec.to_dict()


def test_lint_clean():
    from connectors.spec import ConnectorSpec

    assert ConnectorSpec.from_yaml(REST_SPEC_YAML).lint() == []


def test_lint_flags_missing_required_config():
    from connectors.spec import ConnectorSpec

    spec = ConnectorSpec.from_yaml(REST_SPEC_YAML)
    spec.config.pop("url")
    assert any("url" in i.lower() for i in spec.lint())


def test_lint_flags_unknown_record_type():
    from connectors.spec import ConnectorSpec

    spec = ConnectorSpec.from_yaml(REST_SPEC_YAML)
    spec.record_type = "not_a_real_type"
    assert any("record_type" in i.lower() for i in spec.lint())


def test_lint_flags_unknown_connector_type():
    from connectors.spec import ConnectorSpec

    spec = ConnectorSpec.from_yaml(REST_SPEC_YAML)
    spec.connector_type = "FTP_MAGIC"
    assert any("connector_type" in i.lower() for i in spec.lint())


def test_unknown_top_level_key_rejected():
    from connectors.spec import ConnectorSpec, SpecError

    with pytest.raises(SpecError):
        ConnectorSpec.from_dict({"source_id": "x", "wat": 1})


def test_to_config_builds_rest_config():
    from connectors.base import RecordType, SourceType
    from connectors.rest_connector import RestConfig
    from connectors.spec import ConnectorSpec

    cfg = ConnectorSpec.from_yaml(REST_SPEC_YAML).to_config()
    assert isinstance(cfg, RestConfig)
    assert cfg.source_id == "demo_rest"
    assert cfg.record_type == RecordType.DRUG
    assert cfg.source_type == SourceType.REST  # generic kind; identity is source_id
    assert cfg.url == "https://example.com/api/drugs"
    assert cfg.field_map == {"generic_name": "name"}


def test_build_connector_from_spec_rest():
    from connectors.rest_connector import RestConnector
    from connectors.spec import ConnectorSpec, build_connector_from_spec

    conn = build_connector_from_spec(ConnectorSpec.from_yaml(REST_SPEC_YAML))
    assert isinstance(conn, RestConnector)
    assert conn.config.source_id == "demo_rest"


def test_csv_spec_builds_csv_connector():
    from connectors.csv_connector import CsvConnector
    from connectors.spec import ConnectorSpec, build_connector_from_spec

    spec = ConnectorSpec.from_dict({
        "source_id": "demo_csv", "source_name": "Demo CSV",
        "connector_type": "CSV_FILE", "record_type": "company",
        "config": {"url": "https://example.com/x.csv", "external_id_field": "cik"},
    })
    assert spec.lint() == []
    assert isinstance(build_connector_from_spec(spec), CsvConnector)


def test_rss_spec_builds_rss_connector():
    from connectors.rss_connector import RssConnector
    from connectors.spec import ConnectorSpec, build_connector_from_spec

    spec = ConnectorSpec.from_dict({
        "source_id": "demo_rss", "source_name": "Demo RSS",
        "connector_type": "RSS", "record_type": "event",
        "config": {"url": "https://example.com/feed.xml"},
    })
    assert spec.lint() == []
    assert isinstance(build_connector_from_spec(spec), RssConnector)


def test_unsupported_runtime_type_raises_on_build():
    # WEB_SCRAPE is a valid taxonomy type (persists/drafts fine) but has no
    # Phase-1 runtime connector, so the dynamic loader must fail loudly.
    from connectors.spec import ConnectorSpec, SpecError, build_connector_from_spec

    spec = ConnectorSpec.from_dict({
        "source_id": "scrape1", "source_name": "Scrape",
        "connector_type": "WEB_SCRAPE", "record_type": "drug", "config": {},
    })
    with pytest.raises(SpecError):
        build_connector_from_spec(spec)


def test_seed_example_spec_lints_clean():
    # the shipped example spec must itself be valid (it's the template users copy)
    from pathlib import Path

    from connectors.spec import ConnectorSpec

    example = Path(__file__).resolve().parents[1] / "connectors" / "specs" / "example_rest.yaml"
    assert example.exists(), f"missing seed example at {example}"
    assert ConnectorSpec.load(example).lint() == []
