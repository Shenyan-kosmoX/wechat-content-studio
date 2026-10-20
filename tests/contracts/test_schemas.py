from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from wechat_studio.contracts import ContractValidator, SCHEMA_NAMES, SchemaLoader, load_contract_document
from wechat_studio.errors import UnsupportedSchemaVersionError


FIXTURES = Path(__file__).parent / "fixtures"
VERSION_FIELDS = {
    "project": "project_schema_version",
    "material-manifest": "material_manifest_schema_version",
    "article-plan": "article_plan_schema_version",
    "writing-profile": "writing_profile_schema_version",
    "layout-style": "layout_style_schema_version",
    "style-pack": "style_pack_schema_version",
    "preset": "preset_schema_version",
    "delivery-report": "delivery_report_schema_version",
    "cli-result": "cli_result_schema_version",
}


def valid_document(schema_name: str) -> dict:
    return load_contract_document(FIXTURES / f"{schema_name}.valid.yaml")


@pytest.fixture(scope="module")
def validator() -> ContractValidator:
    return ContractValidator()


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_schema_itself_is_valid(schema_name: str) -> None:
    schema = SchemaLoader().load(schema_name)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_valid_fixture_passes(validator: ContractValidator, schema_name: str) -> None:
    result = validator.validate(valid_document(schema_name), schema_name)
    assert result.valid, result.to_dict()


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_missing_schema_version_is_rejected(
    validator: ContractValidator, schema_name: str
) -> None:
    document = valid_document(schema_name)
    del document[VERSION_FIELDS[schema_name]]

    result = validator.validate(document, schema_name)

    assert not result.valid
    assert any(issue.rule == "required" for issue in result.issues)


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_unknown_top_level_field_is_rejected(
    validator: ContractValidator, schema_name: str
) -> None:
    document = valid_document(schema_name)
    document["unexpected_field"] = True

    result = validator.validate(document, schema_name)

    assert not result.valid
    assert any(issue.rule == "additionalProperties" for issue in result.issues)


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_unsupported_version_has_stable_error(
    validator: ContractValidator, schema_name: str
) -> None:
    document = valid_document(schema_name)
    document[VERSION_FIELDS[schema_name]] = "2.0"

    with pytest.raises(UnsupportedSchemaVersionError) as raised:
        validator.validate_or_raise(document, schema_name)

    assert raised.value.code == "WCS-CONTRACT-005"
    assert raised.value.context["actual"] == "2.0"


def make_domain_invalid(schema_name: str) -> dict:
    document = deepcopy(valid_document(schema_name))
    if schema_name == "project":
        document["paths"]["article"] = "../outside.md"
    elif schema_name == "material-manifest":
        document["items"][1]["id"] = "TEXT-001"
    elif schema_name == "article-plan":
        document["blocks"][1]["placement"]["after"] = "BLOCK-999"
    elif schema_name == "writing-profile":
        document["paragraph_length"] = {
            "minimum_characters": 300,
            "maximum_characters": 100,
        }
    elif schema_name == "layout-style":
        document["component_directory"] = "C:/components"
    elif schema_name == "style-pack":
        document["layer"] = "builtin"
        document["maturity"] = "validated"
    elif schema_name == "preset":
        document["layout_style"]["version"] = "v1"
    elif schema_name == "delivery-report":
        document["status"] = "WECHAT_VALIDATED"
    elif schema_name == "cli-result":
        document["error"] = {
            "code": "WCS-CLI-001",
            "message": "Impossible mixed state",
            "context": {},
        }
    else:  # pragma: no cover - guarded by SCHEMA_NAMES
        raise AssertionError(schema_name)
    return document


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_domain_invalid_variant_is_rejected(
    validator: ContractValidator, schema_name: str
) -> None:
    result = validator.validate(make_domain_invalid(schema_name), schema_name)
    assert not result.valid, schema_name
