"""A request the API cannot read (422) is answered field by field without sending the submitted input back."""

from fastapi.testclient import TestClient

from backend.app.main import app

SECRET = "Never-echo-this-password-2026!"


def test_a_422_names_the_field_and_the_problem_but_never_echoes_the_input():
    client = TestClient(app)
    # A body of the wrong shape: FastAPI's default answer would carry the whole body back as "input".
    wrong_shape = client.post("/api/v1/auth/signin", json=[{"password": SECRET}] * 50)
    assert wrong_shape.status_code == 422, wrong_shape.text
    assert SECRET not in wrong_shape.text
    detail = wrong_shape.json()["detail"]
    assert detail and all("input" not in error for error in detail)
    assert detail[0]["loc"] == ["body"] and detail[0]["msg"] and detail[0]["type"]

    # A field of the wrong type: the location and the message stay, as the app shows them ("email: ...").
    wrong_field = client.post("/api/v1/auth/signin", json={"email": ["x"], "password": SECRET})
    assert wrong_field.status_code == 422, wrong_field.text
    assert SECRET not in wrong_field.text
    errors = wrong_field.json()["detail"]
    assert any(error["loc"] == ["body", "email"] and error["msg"] for error in errors)
    assert all("input" not in error for error in errors)

    # Text that is not JSON at all.
    broken = client.post(
        "/api/v1/auth/signin", content=f'{{"password": "{SECRET}"', headers={"Content-Type": "application/json"}
    )
    assert broken.status_code == 422, broken.text
    assert SECRET not in broken.text
    assert broken.json()["detail"][0]["type"] == "json_invalid"
