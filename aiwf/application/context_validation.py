"""Context validation for workflow initialization.

Validates context dict against profile-defined schemas.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class ValidationError:
    """A single validation error."""
    field: str
    message: str


def _validate_string(field: str, value: Any, rules: dict[str, Any]) -> ValidationError | None:
    """Validate string type."""
    if not isinstance(value, str):
        return ValidationError(
            field=field,
            message=f"Expected string, got {type(value).__name__}"
        )
    return None


def _validate_int(field: str, value: Any, rules: dict[str, Any]) -> ValidationError | None:
    """Validate int type."""
    if not isinstance(value, int):
        return ValidationError(
            field=field,
            message=f"Expected int, got {type(value).__name__}"
        )
    return None


def _validate_bool(field: str, value: Any, rules: dict[str, Any]) -> ValidationError | None:
    """Validate bool type."""
    if not isinstance(value, bool):
        return ValidationError(
            field=field,
            message=f"Expected bool, got {type(value).__name__}"
        )
    return None


def _validate_path(field: str, value: Any, rules: dict[str, Any]) -> ValidationError | None:
    """Validate path type with optional existence check."""
    if not isinstance(value, str):
        return ValidationError(
            field=field,
            message=f"Expected path string, got {type(value).__name__}"
        )
    if rules.get("exists"):
        path = Path(value)
        if not path.exists():
            return ValidationError(
                field=field,
                message=f"Path does not exist: {value}"
            )
        if not path.is_file():
            return ValidationError(
                field=field,
                message=f"Path is not a file: {value}"
            )
    return None


# Type validator dispatch table
TypeValidator = Callable[[str, Any, dict[str, Any]], ValidationError | None]
TYPE_VALIDATORS: dict[str, TypeValidator] = {
    "string": _validate_string,
    "int": _validate_int,
    "bool": _validate_bool,
    "path": _validate_path,
}


def _validate_type(field: str, value: Any, rules: dict[str, Any]) -> ValidationError | None:
    """Validate value against type rule using dispatch table."""
    field_type = rules.get("type", "string")
    validator = TYPE_VALIDATORS.get(field_type)
    if validator:
        return validator(field, value, rules)
    return None


def _validate_choices(field: str, value: Any, rules: dict[str, Any]) -> ValidationError | None:
    """Validate value against choices constraint."""
    if "choices" in rules and value not in rules["choices"]:
        return ValidationError(
            field=field,
            message=f"Must be one of {rules['choices']}, got '{value}'"
        )
    return None


def validate_context(
    schema: dict[str, dict[str, Any]],
    context: dict[str, Any]
) -> list[ValidationError]:
    """Validate context against schema.

    Args:
        schema: Dict of field_name -> rules (type, required, choices, exists)
        context: The context dict to validate

    Returns:
        List of ValidationError, empty if valid
    """
    errors = []

    for field, rules in schema.items():
        value = context.get(field)

        # Required check
        if rules.get("required") and value is None:
            errors.append(ValidationError(
                field=field,
                message="Required field missing"
            ))
            continue

        if value is None:
            continue  # Optional field not provided

        # Type validation
        type_error = _validate_type(field, value, rules)
        if type_error:
            errors.append(type_error)

        # Choices validation
        choices_error = _validate_choices(field, value, rules)
        if choices_error:
            errors.append(choices_error)

    return errors