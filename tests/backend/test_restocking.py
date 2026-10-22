"""
Tests for restocking order API endpoints.
"""
from datetime import datetime

import pytest

from main import restocking_orders


@pytest.fixture(autouse=True)
def reset_restocking_orders():
    """Keep in-memory submitted orders isolated between tests."""
    restocking_orders.clear()
    yield
    restocking_orders.clear()


class TestRestockingEndpoints:
    """Test suite for restocking order endpoints."""

    def test_get_submitted_orders_starts_empty(self, client):
        response = client.get("/api/restocking-orders")

        assert response.status_code == 200
        assert response.json() == []

    def test_create_restocking_order(self, client):
        response = client.post(
            "/api/restocking-orders",
            json={
                "budget": 1000,
                "items": [{"item_sku": "TMP-201", "quantity": 10}]
            }
        )

        assert response.status_code == 201
        order = response.json()
        assert order["total_cost"] == 895
        assert order["budget"] == 1000
        assert order["delivery_lead_time_days"] == 2
        assert order["items"] == [{
            "item_sku": "TMP-201",
            "item_name": "Temperature Sensor Module",
            "quantity": 10,
            "unit_cost": 89.5,
            "line_total": 895
        }]

        submitted_at = datetime.fromisoformat(order["submitted_at"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery_date"])
        assert (expected_delivery - submitted_at).days == 2

        listed_orders = client.get("/api/restocking-orders").json()
        assert listed_orders == [order]

    def test_create_restocking_order_rejects_over_budget(self, client):
        response = client.post(
            "/api/restocking-orders",
            json={
                "budget": 100,
                "items": [{"item_sku": "TMP-201", "quantity": 2}]
            }
        )

        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()
        assert client.get("/api/restocking-orders").json() == []

    def test_create_restocking_order_rejects_unknown_inventory_item(self, client):
        response = client.post(
            "/api/restocking-orders",
            json={
                "budget": 1000,
                "items": [{"item_sku": "UNKNOWN", "quantity": 1}]
            }
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "payload",
        [
            {"budget": 0, "items": [{"item_sku": "TMP-201", "quantity": 1}]},
            {"budget": 1000, "items": []},
            {"budget": 1000, "items": [{"item_sku": "TMP-201", "quantity": 0}]}
        ]
    )
    def test_create_restocking_order_validates_request(self, client, payload):
        response = client.post("/api/restocking-orders", json=payload)

        assert response.status_code == 422
