import pytest

from pheromone.seed.signatures import signature

DEP = "PydanticDeprecatedSince20"

CASES = [
    ("PydanticImportError", "`BaseSettings` has been moved to the `pydantic-settings` package.", "", "base-settings"),
    (DEP, "Pydantic V1 style `@validator` validators are deprecated.", "def f(cls, v, values):", "validator-values"),
    (DEP, "Pydantic V1 style `@validator` validators are deprecated.", "def f(cls, v):", "validator"),
    (DEP, "Pydantic V1 style `@root_validator` validators are deprecated.", "", "root-validator"),
    (DEP, "`json_encoders` is deprecated.", "", "json-encoders"),
    (DEP, "Support for class-based `config` is deprecated, use ConfigDict instead.", "", "config-class"),
    ("PydanticUserError", "To define root models, use `pydantic.RootModel` rather than a field called '__root__'", "", "custom-root"),
    (DEP, "The `update_forward_refs` method is deprecated; use `model_rebuild` instead.", "", "forward-refs"),
    (DEP, "The `validate_arguments` method is deprecated; use `validate_call` instead.", "", "validate-arguments"),
    (DEP, "The `parse_raw` method is deprecated; if your data is JSON use `model_validate_json`", "", "parse-raw"),
    (DEP, "The `parse_obj` method is deprecated; use `model_validate` instead.", "", "parse-obj"),
    (DEP, "The `from_orm` method is deprecated; set `model_config['from_attributes']=True`", "", "from-orm"),
    (DEP, "The `schema` method is deprecated; use `model_json_schema` instead.", "", "schema-call"),
    (DEP, "The `copy` method is deprecated; use `model_copy` instead.", "", "copy-call"),
    (DEP, "The `construct` method is deprecated; use `model_construct` instead.", "", "construct-call"),
    (DEP, "The `__fields__` attribute is deprecated, use the `model_fields` class property instead.", "", "fields-attr"),
    (DEP, "The `dict` method is deprecated; use `model_dump` instead.", "", "dict-call"),
    (DEP, "The `json` method is deprecated; use `model_dump_json` instead.", "", "json-call"),
    ("AssertionError", "assert 1 == 2", "", "other:AssertionError"),
]


@pytest.mark.parametrize("exc,msg,src,expected", CASES)
def test_signature(exc, msg, src, expected):
    assert signature(exc, msg, src) == expected


def test_no_paths_in_signature():
    sig = signature("ImportError", "cannot import name 'x' from 'robusta_krr/core/models.py'")
    assert "/" not in sig
