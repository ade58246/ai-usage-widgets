from __future__ import annotations

import json
import sys


def send(message: dict[str, object]) -> None:
    print(json.dumps(message, separators=(",", ":")), flush=True)


def main() -> int:
    auth_required = "--auth-required" in sys.argv
    initialized = False
    logged_in = not auth_required
    rate_reads = 0

    for line in sys.stdin:
        message = json.loads(line)
        method = message.get("method")
        request_id = message.get("id")

        if method == "initialize":
            send({"id": request_id, "result": {"userAgent": "fake"}})
        elif method == "initialized":
            initialized = True
        elif not initialized:
            send({"id": request_id, "error": {"code": -32000, "message": "Not initialized"}})
        elif method == "account/read":
            account = {"type": "chatgpt", "email": "test@example.com", "planType": "plus"}
            send(
                {
                    "id": request_id,
                    "result": {
                        "account": account if logged_in else None,
                        "requiresOpenaiAuth": True,
                    },
                }
            )
        elif method == "account/login/start":
            logged_in = True
            send(
                {
                    "id": request_id,
                    "result": {
                        "type": "chatgpt",
                        "loginId": "fake-login",
                        "authUrl": "https://chatgpt.com/fake-login",
                    },
                }
            )
            send(
                {
                    "method": "account/login/completed",
                    "params": {"loginId": "fake-login", "success": True, "error": None},
                }
            )
        elif method == "account/rateLimits/read":
            rate_reads += 1
            used = 25 if rate_reads == 1 else 30
            send(
                {
                    "id": request_id,
                    "result": {
                        "rateLimits": {
                            "limitId": "codex",
                            "primary": {
                                "usedPercent": used,
                                "windowDurationMins": 300,
                                "resetsAt": 2_000_000_000,
                            },
                        }
                    },
                }
            )
            if rate_reads == 1:
                send(
                    {
                        "method": "account/rateLimits/updated",
                        "params": {"rateLimits": {"limitId": "codex"}},
                    }
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
