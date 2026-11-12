import uuid

import pytest
from fastapi.testclient import TestClient

from tests.helpers import (
    admin_tokens,
    auth_header,
    count_queries,
    get_my_driver,
    onboard_driver,
    register,
    review,
    set_availability,
)

PENDING_URL = "/api/v1/admin/drivers/pending"
USERS_URL = "/api/v1/admin/users"


# --- Access control ----------------------------------------------------------
def _admin_requests() -> list[tuple[str, str, dict | None]]:
    return [
        ("GET", USERS_URL, None),
        ("GET", PENDING_URL, None),
        ("PATCH", f"/api/v1/admin/drivers/{uuid.uuid4()}/approval", {"status": "APPROVED"}),
    ]


@pytest.mark.parametrize("method, url, body", _admin_requests())
def test_admin_endpoints_reject_anonymous_users(
    client: TestClient, method: str, url: str, body: dict | None
) -> None:
    assert client.request(method, url, json=body).status_code == 401


@pytest.mark.parametrize("method, url, body", _admin_requests())
def test_admin_endpoints_reject_riders_and_drivers(
    client: TestClient, rider_tokens: dict, method: str, url: str, body: dict | None
) -> None:
    rider = client.request(method, url, json=body, headers=auth_header(rider_tokens["access_token"]))
    assert rider.status_code == 403

    driver_tokens, _ = onboard_driver(client)
    driver = client.request(method, url, json=body, headers=auth_header(driver_tokens["access_token"]))
    assert driver.status_code == 403


# --- Pending queue -----------------------------------------------------------
def test_pending_list_contains_only_pending_drivers_with_user_and_vehicle(
    client: TestClient,
) -> None:
    admin = admin_tokens(client)
    profiles = [onboard_driver(client, n)[1] for n in (1, 2, 3)]
    review(client, admin, profiles[0]["id"])  # approve driver 1

    response = client.get(PENDING_URL, headers=auth_header(admin["access_token"]))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    emails = [item["user"]["email"] for item in body["items"]]
    assert emails == ["driver2@example.com", "driver3@example.com"]  # oldest first
    assert all(item["vehicle"] is not None for item in body["items"])
    assert "password_hash" not in response.text


def test_pending_list_pagination(client: TestClient) -> None:
    admin = admin_tokens(client)
    for n in (1, 2, 3):
        onboard_driver(client, n)
    headers = auth_header(admin["access_token"])

    page2 = client.get(PENDING_URL, params={"page": 2, "page_size": 2}, headers=headers).json()
    assert page2["total"] == 3
    assert len(page2["items"]) == 1
    assert client.get(PENDING_URL, params={"page_size": 0}, headers=headers).status_code == 422
    assert client.get(PENDING_URL, params={"page_size": 101}, headers=headers).status_code == 422


def test_pending_list_does_not_run_n_plus_one_queries(client: TestClient) -> None:
    admin = admin_tokens(client)
    headers = auth_header(admin["access_token"])
    onboard_driver(client, 1)

    with count_queries() as few:
        assert client.get(PENDING_URL, headers=headers).status_code == 200

    for n in range(2, 7):
        onboard_driver(client, n)

    with count_queries() as many:
        assert client.get(PENDING_URL, headers=headers).status_code == 200

    assert len(many) == len(few)


# --- Approval ----------------------------------------------------------------
def test_approving_a_driver_records_the_reviewer(client: TestClient) -> None:
    admin = admin_tokens(client)
    tokens, profile = onboard_driver(client)

    response = review(client, admin, profile["id"])
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "APPROVED"
    assert body["reviewed_at"] is not None

    admin_id = client.get("/api/v1/users/me", headers=auth_header(admin["access_token"])).json()["id"]
    assert body["reviewed_by_id"] == admin_id
    assert get_my_driver(client, tokens).json()["verification_status"] == "APPROVED"


def test_approval_is_idempotent(client: TestClient) -> None:
    admin = admin_tokens(client)
    _, profile = onboard_driver(client)
    first = review(client, admin, profile["id"]).json()
    second = review(client, admin, profile["id"])
    assert second.status_code == 200
    assert second.json()["reviewed_at"] == first["reviewed_at"]  # untouched


def test_rejection_requires_a_reason(client: TestClient) -> None:
    admin = admin_tokens(client)
    _, profile = onboard_driver(client)
    assert review(client, admin, profile["id"], "REJECTED").status_code == 422
    assert review(client, admin, profile["id"], "REJECTED", "   ").status_code == 422


def test_rejecting_an_online_driver_forces_them_offline(client: TestClient) -> None:
    admin = admin_tokens(client)
    tokens, profile = onboard_driver(client)
    review(client, admin, profile["id"])
    set_availability(client, tokens, "ONLINE")

    response = review(client, admin, profile["id"], "REJECTED", "License expired")
    assert response.status_code == 200
    body = get_my_driver(client, tokens).json()
    assert body["verification_status"] == "REJECTED"
    assert body["availability"] == "OFFLINE"
    assert body["rejection_reason"] == "License expired"


def test_re_approval_clears_the_rejection_reason(client: TestClient) -> None:
    admin = admin_tokens(client)
    tokens, profile = onboard_driver(client)
    review(client, admin, profile["id"], "REJECTED", "Blurry photo")
    review(client, admin, profile["id"], "APPROVED")
    assert get_my_driver(client, tokens).json()["rejection_reason"] is None


def test_review_unknown_driver_returns_404_and_bad_id_returns_422(client: TestClient) -> None:
    admin = admin_tokens(client)
    assert review(client, admin, str(uuid.uuid4())).status_code == 404
    assert review(client, admin, "not-a-uuid").status_code == 422


@pytest.mark.parametrize("body", [{"status": "PENDING"}, {"status": "MAYBE"}, {}])
def test_invalid_approval_payload_returns_422(client: TestClient, body: dict) -> None:
    admin = admin_tokens(client)
    _, profile = onboard_driver(client)
    response = client.patch(
        f"/api/v1/admin/drivers/{profile['id']}/approval",
        json=body,
        headers=auth_header(admin["access_token"]),
    )
    assert response.status_code == 422


# --- Users list --------------------------------------------------------------
def test_admin_can_list_and_filter_users(client: TestClient) -> None:
    admin = admin_tokens(client)
    register(client, email="rider@example.com")
    onboard_driver(client, 1)
    onboard_driver(client, 2)
    headers = auth_header(admin["access_token"])

    everyone = client.get(USERS_URL, headers=headers).json()
    assert everyone["total"] == 4  # admin + rider + 2 drivers
    assert "password_hash" not in str(everyone)

    drivers = client.get(USERS_URL, params={"role": "DRIVER"}, headers=headers).json()
    assert drivers["total"] == 2
    assert all(item["role"] == "DRIVER" for item in drivers["items"])

    assert client.get(USERS_URL, params={"role": "HACKER"}, headers=headers).status_code == 422