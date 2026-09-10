from uuid import UUID

from fastapi.testclient import TestClient

from app.api.routes import router
from app.core.errors import DomainError
from app.core.ids import generate_correlation_id, generate_request_id
from app.main import create_app


def test_centralized_identifiers_are_distinct_uuid4_values():
    request_id = generate_request_id()
    correlation_id = generate_correlation_id()

    assert request_id != correlation_id
    assert UUID(request_id).version == 4
    assert UUID(correlation_id).version == 4


def test_domain_error_returns_safe_structured_payload(settings):
    app = create_app(settings)

    @app.get("/_test/domain-error")
    def failing_endpoint():
        raise DomainError(
            code="dependency_unavailable",
            message="The market feed is temporarily unavailable",
            retryable=True,
            dependency="market-feed",
            evidence="api_key=must-never-be-returned",
        )

    with TestClient(app) as client:
        response = client.get("/_test/domain-error")

    assert response.status_code == 400
    assert response.headers["X-Correlation-ID"] == response.json()["correlation_id"]
    assert response.json() == {
        "code": "dependency_unavailable",
        "message": "The market feed is temporarily unavailable",
        "retryable": True,
        "dependency": "market-feed",
        "evidence": None,
        "correlation_id": response.headers["X-Correlation-ID"],
    }


def test_system_aliases_share_the_existing_contracts(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/health").json() == client.get("/healthz").json()
        ready = client.get("/ready")
        readyz = client.get("/readyz")
        assert ready.status_code == readyz.status_code
        assert ready.json()["status"] == readyz.json()["status"]
        assert ready.json()["live_trading_enabled"] is False
        assert readyz.json()["live_trading_enabled"] is False
        alias_capabilities = client.get("/api/system/capabilities").json()
        versioned_capabilities = client.get("/v1/system/capabilities").json()
        assert [
            (item["name"], item["required"], item["status"], item["version"], item["reason"])
            for item in alias_capabilities
        ] == [
            (item["name"], item["required"], item["status"], item["version"], item["reason"])
            for item in versioned_capabilities
        ]

        endpoints = {route.path: route.endpoint for route in router.routes}

    assert endpoints["/health"] is endpoints["/healthz"]
    assert endpoints["/ready"] is endpoints["/readyz"]
    assert endpoints["/api/system/capabilities"] is endpoints["/v1/system/capabilities"]
