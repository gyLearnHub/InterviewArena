from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from app.harness.contracts import ValidationStatus


class OutputValidationResult(BaseModel):
    validation_status: ValidationStatus
    errors: list[str] = []
    normalized_output: Any = None


class OutputValidator:
    def validate(
        self,
        output: Any,
        expected_schema: dict[str, Any] | type[BaseModel] | None,
    ) -> OutputValidationResult:
        if output is None or output == "":
            return OutputValidationResult(
                validation_status="failed",
                errors=["output is empty"],
                normalized_output=output,
            )
        if expected_schema is None:
            return OutputValidationResult(validation_status="passed", normalized_output=output)
        if isinstance(expected_schema, type) and issubclass(expected_schema, BaseModel):
            return self._validate_pydantic_model(output, expected_schema)
        if isinstance(expected_schema, dict):
            return self._validate_json_schema_subset(output, expected_schema)
        return OutputValidationResult(
            validation_status="warning",
            errors=["unsupported expected schema type"],
            normalized_output=output,
        )

    def _validate_pydantic_model(
        self,
        output: Any,
        model_type: type[BaseModel],
    ) -> OutputValidationResult:
        try:
            normalized = model_type.model_validate(output)
        except ValidationError as exc:
            return OutputValidationResult(
                validation_status="failed",
                errors=[error["msg"] for error in exc.errors()],
                normalized_output=output,
            )
        return OutputValidationResult(
            validation_status="passed",
            normalized_output=normalized.model_dump(mode="json"),
        )

    def _validate_json_schema_subset(
        self,
        output: Any,
        schema: dict[str, Any],
    ) -> OutputValidationResult:
        errors: list[str] = []
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        if schema.get("type") == "object" and not isinstance(output, dict):
            errors.append("output must be an object")
        if isinstance(output, dict):
            for field in required if isinstance(required, list) else []:
                if field not in output or output[field] is None:
                    errors.append(f"missing required field: {field}")
            if isinstance(properties, dict):
                for field, definition in properties.items():
                    if field in output:
                        errors.extend(_validate_field(field, output[field], definition))
            errors.extend(_validate_score_fields(output))
        return OutputValidationResult(
            validation_status="failed" if errors else "passed",
            errors=errors,
            normalized_output=output,
        )


def _validate_field(field: str, value: Any, definition: Any) -> list[str]:
    if not isinstance(definition, dict) or value is None:
        return []
    expected_type = definition.get("type")
    if expected_type == "string" and not isinstance(value, str):
        return [f"{field} must be a string"]
    if expected_type == "integer" and not isinstance(value, int):
        return [f"{field} must be an integer"]
    if expected_type == "number" and not isinstance(value, (int, float)):
        return [f"{field} must be a number"]
    if expected_type == "array" and not isinstance(value, list):
        return [f"{field} must be an array"]
    if expected_type == "object" and not isinstance(value, dict):
        return [f"{field} must be an object"]
    return []


def _validate_score_fields(output: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("score", "total_score"):
        value = output.get(key)
        if value is not None and (not isinstance(value, (int, float)) or value < 0 or value > 100):
            errors.append(f"{key} must be between 0 and 100")
    return errors
