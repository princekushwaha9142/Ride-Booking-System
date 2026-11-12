import pytest
from fastapi.testclient import TestClient

from tests.helpers import (
    auth_header,
    driver_payload,
    get_my_driver,
    login_tokens,
    onboard_driver,
    admin_tokens,
    register,
    review,
    set_active_ride_in_db,
    set_availability,
)

PROFILE_URL = "/api/v1/drivers/me"


# --- Application -------------------------------------------------------------
def test_driver_application_starts_pending_and_offline(client: TestClient) -> None:
    _, profile = onboard_driver(client)
    assert profile["verification_status"] == "PENDING"
    assert profile["availability"] == "OFFLINE"
    assert profile["rejection_reason"] is None
    assert profile["vehicle"]["registration_number"] == "RJ14CD0001"
    assert profile["vehicle"]["is_active"] is True


def test_plate_and_license_are_normalized(client: TestClient) -> None:
    register(client, email="d@example.com", role="DRIVER")
    tokens = login_tokens(client, "d@example.com")
    response = client.post(
        PROFILE_URL,
        json=driver_payload(license_number="rj14 2011-0012345", registration_number="rj14 cd-1234"),
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 201
    assert response.json()["license_number"] == "RJ1420110012345"
    assert response.json()["vehicle"]["registration_number"] == "RJ14CD1234"


def test_rider_cannot_submit_driver_application(client: TestClient, rider_tokens: dict) -> None:
    response = client.post(
        PROFILE_URL, json=driver_payload(), headers=auth_header(rider_tokens["access_token"])
    )
    assert response.status_code == 403


def test_driver_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get(PROFILE_URL).status_code == 401
    assert client.post(PROFILE_URL, json=driver_payload()).status_code == 401


def test_submitting_a_second_application_returns_409(client: TestClient) -> None:
    tokens, _ = onboard_driver(client)
    response = client.post(
        PROFILE_URL,
        json=driver_payload(license_number="ZZ9999999999", registration_number="ZZ99ZZ9999"),
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["error"]["message"]


def test_duplicate_license_across_drivers_returns_409(client: TestClient) -> None:
    onboard_driver(client, 1)
    register(client, email="other@example.com", role="DRIVER")
    other = login_tokens(client, "other@example.com")
    response = client.post(
        PROFILE_URL,
        json=driver_payload(license_number="RJ1420110012301", registration_number="XX11XX1111"),
        headers=auth_header(other["access_token"]),
    )
    assert response.status_code == 409
    assert "License" in response.json()["error"]["message"]


def test_duplicate_vehicle_registration_returns_409(client: TestClient) -> None:
    onboard_driver(client, 1)
    register(client, email="other@example.com", role="DRIVER")
    other = login_tokens(client, "other@example.com")
    response = client.post(
        PROFILE_URL,
        json=driver_payload(license_number="QQ1111111111", registration_number="rj14-cd 0001"),
        headers=auth_header(other["access_token"]),
    )
    assert response.status_code == 409
    assert "registration" in response.json()["error"]["message"]


@pytest.mark.parametrize(
    "payload",
    [
        driver_payload(registration_number="!!"),
        driver_payload(vehicle_type="TRUCK"),
        driver_payload(license_number="ABC"),
        driver_payload(make="   "),
        {"license_number": "RJ1420110012345"},  # vehicle missing
    ],
)
def test_invalid_application_returns_422(client: TestClient, payload: dict) -> None:
    register(client, email="d@example.com", role="DRIVER")
    tokens = login_tokens(client, "d@example.com")
    response = client.post(PROFILE_URL, json=payload, headers=auth_header(tokens["access_token"]))
    assert response.status_code == 422


def test_get_profile_returns_404_before_application(client: TestClient) -> None:
    register(client, email="d@example.com", role="DRIVER")
    tokens = login_tokens(client, "d@example.com")
    assert get_my_driver(client, tokens).status_code == 404


# --- Availability ------------------------------------------------------------
def test_unapproved_driver_cannot_go_online(client: TestClient) -> None:
    tokens, _ = onboard_driver(client)
    response = set_availability(client, tokens, "ONLINE")
    assert response.status_code == 403
    assert get_my_driver(client, tokens).json()["availability"] == "OFFLINE"


def test_approved_driver_can_toggle_availability_idempotently(client: TestClient) -> None:
    tokens, profile = onboard_driver(client)
    assert review(client, admin_tokens(client), profile["id"]).status_code == 200

    assert set_availability(client, tokens, "ONLINE").json()["availability"] == "ONLINE"
    assert set_availability(client, tokens, "ONLINE").status_code == 200  # idempotent
    assert get_my_driver(client, tokens).json()["availability"] == "ONLINE"
    assert set_availability(client, tokens, "OFFLINE").json()["availability"] == "OFFLINE"


def test_rejected_driver_cannot_go_online(client: TestClient) -> None:
    tokens, profile = onboard_driver(client)
    review(client, admin_tokens(client), profile["id"], "REJECTED", "Blurry documents")
    assert set_availability(client, tokens, "ONLINE").status_code == 403


def test_invalid_availability_value_returns_422(client: TestClient) -> None:
    tokens, _ = onboard_driver(client)
    response = client.patch(
        "/api/v1/drivers/me/availability",
        json={"availability": "BUSY"},
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 422


def test_cannot_go_offline_or_edit_profile_during_active_ride(client: TestClient) -> None:
    tokens, profile = onboard_driver(client)
    review(client, admin_tokens(client), profile["id"])
    set_availability(client, tokens, "ONLINE")
    set_active_ride_in_db(profile["id"])

    assert set_availability(client, tokens, "OFFLINE").status_code == 409
    response = client.patch(
        PROFILE_URL,
        json={"license_number": "NEW12345678"},
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 409


# --- Profile updates ---------------------------------------------------------
def test_changing_license_resets_verification_and_goes_offline(client: TestClient) -> None:
    tokens, profile = onboard_driver(client)
    review(client, admin_tokens(client), profile["id"])
    set_availability(client, tokens, "ONLINE")

    response = client.patch(
        PROFILE_URL,
        json={"license_number": "NEW1234567890"},
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["license_number"] == "NEW1234567890"
    assert body["verification_status"] == "PENDING"
    assert body["availability"] == "OFFLINE"
    assert set_availability(client, tokens, "ONLINE").status_code == 403


def test_changing_plate_resets_verification(client: TestClient) -> None:
    tokens, profile = onboard_driver(client)
    review(client, admin_tokens(client), profile["id"])
    response = client.patch(
        PROFILE_URL,
        json={"vehicle": {"registration_number": "RJ14 ZZ 9999"}},
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 200
    assert response.json()["verification_status"] == "PENDING"
    assert response.json()["vehicle"]["registration_number"] == "RJ14ZZ9999"


def test_cosmetic_change_keeps_approval_and_online_status(client: TestClient) -> None:
    tokens, profile = onboard_driver(client)
    review(client, admin_tokens(client), profile["id"])
    set_availability(client, tokens, "ONLINE")

    response = client.patch(
        PROFILE_URL,
        json={"vehicle": {"color": "Black"}},
        headers=auth_header(tokens["access_token"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["vehicle"]["color"] == "Black"
    assert body["verification_status"] == "APPROVED"
    assert body["availability"] == "ONLINE"


def test_empty_patch_returns_422(client: TestClient) -> None:
    tokens, _ = onboard_driver(client)
    response = client.patch(PROFILE_URL, json={}, headers=auth_header(tokens["access_token"]))
    assert response.status_code == 422