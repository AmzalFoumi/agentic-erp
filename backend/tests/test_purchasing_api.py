"""The purchasing routes. Translation only - the rules are tested in services."""

from decimal import Decimal


def test_creating_and_listing_a_supplier(client):
    created = client.post(
        "/suppliers",
        json={
            "name": "API DairyCo",
            "lead_time_days": 3,
            "minimum_order_value": "300.00",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "API DairyCo"

    # Money is a JSON string, not a number. Deliberate, to avoid float64
    # precision loss on Numeric columns - do not "fix" this.
    assert body["minimum_order_value"] == "300.00"
    assert isinstance(body["minimum_order_value"], str)

    listed = client.get("/suppliers")
    assert listed.status_code == 200
    assert "API DairyCo" in [item["name"] for item in listed.json()["items"]]


def test_a_duplicate_supplier_name_is_a_conflict(client):
    client.post("/suppliers", json={"name": "Twice Ltd"})
    again = client.post("/suppliers", json={"name": "Twice Ltd"})
    assert again.status_code == 409
    assert "error" in again.json()


def test_an_unknown_supplier_is_not_found(client):
    response = client.get("/suppliers/999999")
    assert response.status_code == 404
    assert "error" in response.json()


def test_a_partial_update_leaves_other_fields_alone(client):
    created = client.post(
        "/suppliers",
        json={"name": "Partial Ltd", "contact_email": "keep@me.com",
              "lead_time_days": 5},
    ).json()

    updated = client.patch(
        f"/suppliers/{created['id']}", json={"lead_time_days": 9}
    )
    assert updated.status_code == 200
    assert updated.json()["lead_time_days"] == 9
    assert updated.json()["contact_email"] == "keep@me.com"


def test_an_explicit_null_name_is_rejected(client):
    """Omitting a field means 'leave it alone'; sending null used to mean 500."""
    created = client.post("/suppliers", json={"name": "Nullable Ltd"}).json()

    response = client.patch(f"/suppliers/{created['id']}", json={"name": None})
    assert response.status_code == 422


def test_an_explicit_null_contact_email_still_clears_it(client):
    """The contact fields are the ones null is genuinely for."""
    created = client.post(
        "/suppliers", json={"name": "Clearable Ltd", "contact_email": "a@b.com"}
    ).json()

    response = client.patch(f"/suppliers/{created['id']}", json={"contact_email": None})
    assert response.status_code == 200
    assert response.json()["contact_email"] is None


def test_the_reorder_report_is_reachable(client):
    response = client.get("/purchasing/reorder-suggestions")
    assert response.status_code == 200
    body = response.json()
    assert "bundles" in body
    assert "unsourced" in body
    assert "total_value" in body


def test_an_unknown_order_status_filter_is_a_bad_request(client):
    response = client.get("/purchase-orders", params={"status": "banana"})
    assert response.status_code == 400


def test_a_negative_pack_size_is_a_422_not_a_400(client):
    """Schema-level rejection (pack_size < 1) is FastAPI's job, distinct from
    a business-rule refusal - the two must not collapse onto the same code."""
    supplier = client.post("/suppliers", json={"name": "Schema Test Co"}).json()
    response = client.post(
        f"/suppliers/{supplier['id']}/products",
        json={"product_id": 1, "unit_cost": "1.00", "pack_size": 0},
    )
    assert response.status_code == 422


def test_creating_a_supplier_with_a_blank_name_is_a_422(client):
    response = client.post("/suppliers", json={"name": ""})
    assert response.status_code == 422
