"""MercuryAssistantRunner: POST /v1/agent via httpx (stub)."""


class MercuryAssistantRunner:
    """TODO: implement httpx client, idempotency, AssistantTurnResult parsing."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
