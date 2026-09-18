def test_register_returns_token(client):
    response = client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "password123", "captcha_token": "tok"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_register_duplicate_email_returns_409(client):
    body = {"email": "a@example.com", "password": "password123", "captcha_token": "tok"}
    client.post("/auth/register", json=body)
    response = client.post("/auth/register", json=body)
    assert response.status_code == 409


def test_login_wrong_password_returns_401(client):
    client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "password123", "captcha_token": "tok"},
    )
    response = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})
    assert response.status_code == 401


def test_jobs_endpoint_requires_auth(client):
    response = client.get("/jobs")
    assert response.status_code == 401


def test_change_password_flow(client, auth_headers):
    headers = auth_headers()
    response = client.post(
        "/auth/change-password",
        json={"old_password": "password123", "new_password": "new-password456"},
        headers=headers,
    )
    assert response.status_code == 204

    relogin = client.post("/auth/login", json={"email": "a@example.com", "password": "new-password456"})
    assert relogin.status_code == 200
