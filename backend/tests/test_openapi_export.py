from scripts.export_openapi import _contract_source


def test_generated_contract_contains_component_and_operation_types() -> None:
    source = _contract_source(
        {
            "components": {
                "schemas": {
                    "RequestBody": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "enabled": {"type": "boolean"},
                        },
                        "required": ["name"],
                    },
                    "ResponseBody": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["id", "tags"],
                    },
                }
            },
            "paths": {
                "/api/example": {
                    "post": {
                        "operationId": "create_example",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/RequestBody"
                                    }
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/ResponseBody"
                                        }
                                    }
                                }
                            }
                        },
                    }
                }
            },
        }
    )

    assert 'export type ApiSchemas = {' in source
    assert '"RequestBody": { name: string; enabled?: boolean };' in source
    assert '"ResponseBody": { id: number; tags: Array<string> };' in source
    assert (
        '"create_example": { requestBody: ApiSchemas["RequestBody"]; '
        'response: ApiSchemas["ResponseBody"] };'
    ) in source
