from pathlib import Path
from time import monotonic, sleep


def register_from_outbox(client, email: str, password: str, name: str, outbox: Path):
    """Complete a local synthetic signup through the development email outbox."""
    previous = set(outbox.glob("*.txt"))
    headers = {"x-meetflow-client": "1"}
    client.post(
        "/api/auth/register", headers=headers, json={"email": email}
    ).raise_for_status()

    # Both the local ASGI client and ordinary HTTP client may be used here.
    # The dev outbox writes in a background task after an HTTP response.
    limit = monotonic() + 3
    while monotonic() < limit:
        for message in set(outbox.glob("*.txt")) - previous:
            lines = message.read_text(encoding="utf-8").splitlines()
            if not lines or lines[0] != f"To: {email}":
                continue
            for line in lines:
                if "/register/confirm#token=" in line:
                    token = line.split("#token=", 1)[1]
                    client.post(
                        "/api/auth/register/confirm",
                        headers=headers,
                        json={
                            "token": token,
                            "password": password,
                            "display_name": name,
                        },
                    ).raise_for_status()
                    return
        sleep(0.05)
    raise RuntimeError("No verification email arrived in the development outbox.")
