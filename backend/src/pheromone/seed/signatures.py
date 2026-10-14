"""Failure signature: exception + the Pydantic v1 symbol behind it.

Pure and repo-agnostic: a signature never contains a path, so Recipes learned
on one repo match failures in another.
"""

import re

# (signature, pattern over "ExcType: message"). First match wins.
RULES: list[tuple[str, re.Pattern]] = [
    (sig, re.compile(pat, re.IGNORECASE))
    for sig, pat in [
        ("base-settings", r"BaseSettings` has been moved"),
        ("root-validator", r"`@root_validator`"),
        ("validator", r"V1 style `@validator`"),
        ("json-encoders", r"`json_encoders` is deprecated"),
        ("config-class", r"class-based `config` is deprecated"),
        ("custom-root", r"RootModel|__root__"),
        ("forward-refs", r"`update_forward_refs`"),
        ("validate-arguments", r"`validate_arguments`"),
        ("parse-raw", r"`parse_raw`"),
        ("parse-obj", r"`parse_obj`"),
        ("from-orm", r"`from_orm`"),
        ("schema-call", r"The `schema` method"),
        ("copy-call", r"The `copy` method"),
        ("construct-call", r"`construct` method"),
        ("fields-attr", r"`__fields__`"),
        ("dict-call", r"The `dict` method"),
        ("json-call", r"The `json` method"),
        ("generic-model", r"GenericModel"),
        ("field-regex", r"`regex` is removed|regex.*pattern"),
        ("field-extra", r"min_items|max_items|`const`|unique_items"),
        ("optional-default", r"Field required"),
        ("config-key-removed", r"Valid config keys have changed|removed:"),
    ]
]

_VALUES_PARAM = re.compile(r"def\s+\w+\s*\([^)]*\bvalues\b")


def signature(exc_type: str, message: str, source: str = "") -> str:
    """`source` is the code around the innermost repo frame, if available."""
    text = f"{exc_type}: {message}"
    for sig, pat in RULES:
        if pat.search(text):
            if sig == "validator" and _VALUES_PARAM.search(source):
                return "validator-values"
            return sig
    return f"other:{exc_type or 'Error'}"
