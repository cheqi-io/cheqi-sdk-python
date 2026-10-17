"""Webhook subscription management."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from cheqi.http.client import CheqiApiClient
from cheqi.http.request_options import RequestOptions
from cheqi.models.generated.webhook_dto import WebhookDTO


class WebhookService:
    def __init__(self, api_client: CheqiApiClient) -> None:
        self._api_client = api_client

    def update_subscription_url(
        self, subscription_id: UUID, notification_url: str, *, options: Optional[RequestOptions] = None,
    ) -> WebhookDTO:
        if not notification_url.strip():
            raise ValueError("Notification URL is required")
        return self._api_client.update_webhook_subscription_url(
            subscription_id, notification_url, options=options,
        )
