"""Hand-written priors: signature -> competing hypotheses (kind, text).

These are what pheromone chooses between, so most signatures get 2+ options,
including plausible-but-weaker ones. Failures without a template go to the
LLM proposer. Baseline gets the same table.
"""

TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "base-settings": [
        ("settings-import", "Import BaseSettings from pydantic_settings instead of pydantic and keep the class otherwise unchanged."),
        ("settings-config-dict", "Import BaseSettings from pydantic_settings and replace the inner class Config with model_config = SettingsConfigDict(...), keeping env_prefix and other settings."),
    ],
    "validator-values": [
        ("field-validator-info", "Replace @validator with @field_validator plus @classmethod, take info: ValidationInfo and read earlier fields from info.data instead of values."),
        ("model-validator-after", "Replace the field validator with @model_validator(mode='after') that reads and sets fields on self."),
    ],
    "validator": [
        ("field-validator", "Replace @validator with @field_validator plus @classmethod; pre=True becomes mode='before', each_item=True becomes validating the list items in the function, always=True becomes validate_default=True on the Field."),
        ("annotated-validator", "Move the check into an Annotated type with AfterValidator / BeforeValidator."),
    ],
    "root-validator": [
        ("model-validator", "Replace @root_validator with @model_validator; pre=True becomes mode='before' on a classmethod taking the raw dict, otherwise mode='after' on an instance method returning self."),
        ("model-validator-before", "Replace @root_validator with @model_validator(mode='before') on a classmethod that works on the input dict."),
    ],
    "json-encoders": [
        ("field-serializer", "Remove Config.json_encoders; add @field_serializer for the affected fields (or a PlainSerializer in Annotated) that produces the same output, and move other Config keys to model_config = ConfigDict(...)."),
        ("model-serializer", "Remove json_encoders and add a @model_serializer(mode='wrap') that formats datetimes the same way."),
    ],
    "config-class": [
        ("config-dict", "Replace the inner class Config with model_config = ConfigDict(...) and rename keys (orm_mode->from_attributes, allow_population_by_field_name->populate_by_name, anystr_strip_whitespace->str_strip_whitespace, allow_mutation=False->frozen=True)."),
        ("field-level", "Move the setting from class Config to the individual Field(...) definitions (alias=..., etc.) and drop class Config."),
    ],
    "config-key-removed": [
        ("config-dict", "Rename removed config keys to their v2 names in model_config = ConfigDict(...) (allow_mutation=False->frozen=True, orm_mode->from_attributes, fields={...alias}->Field(alias=...))."),
    ],
    "custom-root": [
        ("root-model", "Turn the __root__ model into a pydantic.RootModel[...] subclass and use .root instead of .__root__; parse with model_validate."),
        ("type-adapter", "Replace the __root__ model with a TypeAdapter over the inner type plus a plain helper class."),
    ],
    "forward-refs": [
        ("model-rebuild", "Replace Model.update_forward_refs() with Model.model_rebuild()."),
    ],
    "validate-arguments": [
        ("validate-call", "Replace @validate_arguments with @validate_call."),
    ],
    "parse-obj": [
        ("model-validate", "Replace Model.parse_obj(data) with Model.model_validate(data)."),
        ("constructor", "Replace Model.parse_obj(data) with Model(**data)."),
    ],
    "parse-raw": [
        ("model-validate-json", "Replace Model.parse_raw(body) with Model.model_validate_json(body)."),
        ("json-loads", "Replace Model.parse_raw(body) with Model.model_validate(json.loads(body))."),
    ],
    "from-orm": [
        ("from-attributes", "Set model_config = ConfigDict(from_attributes=True) and replace Model.from_orm(obj) with Model.model_validate(obj)."),
    ],
    "schema-call": [
        ("model-json-schema", "Replace Model.schema() with Model.model_json_schema()."),
    ],
    "copy-call": [
        ("model-copy", "Replace .copy(update=...) with .model_copy(update=...)."),
        ("rebuild", "Replace .copy(update=...) with Model(**{**obj.model_dump(), **update})."),
    ],
    "construct-call": [
        ("model-construct", "Replace Model.construct(**data) with Model.model_construct(**data)."),
    ],
    "fields-attr": [
        ("model-fields", "Replace Model.__fields__ with Model.model_fields; field.required becomes field.is_required(), outer_type_ becomes annotation."),
    ],
    "dict-call": [
        ("model-dump", "Replace .dict(...) with .model_dump(...), keeping the same keyword arguments."),
        ("dict-builtin", "Replace .dict() with dict(obj) and filter keys by hand."),
    ],
    "json-call": [
        ("model-dump-json", "Replace .json(...) with .model_dump_json(...), keeping by_alias and other keyword arguments."),
        ("json-dumps", "Replace .json() with json.dumps(obj.model_dump(mode='json'))."),
    ],
    "generic-model": [
        ("generic-basemodel", "Drop GenericModel; subclass BaseModel and Generic[T] directly."),
    ],
    "field-regex": [
        ("pattern", "Rename regex= to pattern= in Field / constr."),
    ],
    "field-extra": [
        ("length-names", "Rename min_items/max_items to min_length/max_length; replace const with Literal; unique_items with a set type."),
    ],
    "optional-default": [
        ("none-default", "Add an explicit = None default to Optional[...] fields that v1 treated as optional."),
        ("field-default", "Use Field(default=None) on Optional[...] fields."),
    ],
}


def for_signature(sig: str) -> list[tuple[str, str]]:
    return TEMPLATES.get(sig, [])
