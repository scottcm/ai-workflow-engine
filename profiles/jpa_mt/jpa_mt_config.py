from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from aiwf.domain.validation.path_validator import PathValidator, PathValidationError


class StandardsConfig(BaseModel):
    root: str

    @field_validator("root")
    @classmethod
    def expand_and_validate_root(cls, v: str) -> str:
        # Expand ${VAR} using the authoritative utility, and enforce non-empty result.
        try:
            expanded = PathValidator.expand_env_vars(v)
        except PathValidationError as e:
            # Pydantic will wrap this into ValidationError at the model boundary.
            raise ValueError(str(e)) from e

        if not expanded.strip():
            raise ValueError("Standards root cannot be empty after expansion")

        return expanded


class ScopeConfig(BaseModel):
    layers: list[str]
    description: str | None = None

    @field_validator("layers")
    @classmethod
    def validate_layers_non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Layers list cannot be empty")
        return v


class JpaMtConfig(BaseModel):
    # Legacy top-level keys (e.g., artifacts) must be ignored.
    model_config = ConfigDict(extra="ignore")

    standards: StandardsConfig
    scopes: dict[str, ScopeConfig]
    layer_standards: dict[str, list[str]]

    @model_validator(mode="after")
    def validate_layer_standards_structure(self) -> "JpaMtConfig":
        for layer, paths in self.layer_standards.items():
            if paths is None:
                raise ValueError(f"layer_standards['{layer}'] must not be null; use []")

            if not isinstance(paths, list):
                raise ValueError(f"layer_standards['{layer}'] must be a list of strings")

            for path in paths:
                if not isinstance(path, str):
                    raise ValueError(f"layer_standards['{layer}'] entries must be strings")

                try:
                    PathValidator.validate_relative_path_pattern(path)
                except PathValidationError as e:
                    raise ValueError(str(e)) from e

        return self

    @model_validator(mode="after")
    def validate_coverage(self) -> "JpaMtConfig":
        if not self.scopes:
            raise ValueError("Must define at least one scope")

        if not self.layer_standards:
            raise ValueError("Must define at least one layer standard")

        referenced_layers: set[str] = set()
        for scope in self.scopes.values():
            referenced_layers.update(scope.layers)

        has_universal = "_universal" in self.layer_standards

        for layer in referenced_layers:
            if layer not in self.layer_standards and not has_universal:
                raise ValueError(
                    f"Layer '{layer}' is referenced in scopes but not defined in layer_standards "
                    "and no '_universal' fallback exists."
                )

        return self
