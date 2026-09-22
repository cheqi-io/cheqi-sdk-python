from scripts.check_openapi import first_difference


def test_openapi_comparison_ignores_mapping_order() -> None:
    local = {
        "responses": {
            "200": {"description": "Success"},
            "401": {"description": "Unauthorized"},
        }
    }
    remote = {
        "responses": {
            "401": {"description": "Unauthorized"},
            "200": {"description": "Success"},
        }
    }

    assert first_difference(local, remote) is None


def test_openapi_comparison_reports_semantic_changes() -> None:
    local = {"responses": {"200": {"description": "Success"}}}
    remote = {"responses": {"200": {"description": "Changed"}}}

    assert first_difference(local, remote) == (
        "$.responses.200.description: expected 'Success', got 'Changed'"
    )
