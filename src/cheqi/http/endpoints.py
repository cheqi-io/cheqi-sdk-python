"""API endpoint paths for the Cheqi SDK."""

from __future__ import annotations


class Endpoints:
    """Cheqi API endpoint paths."""

    OAUTH_TOKEN = "/oauth2/token"
    CUSTOMER_MATCH = "/recipient/resolve"
    ENCRYPTED_RECEIPT = "/receipt/encrypted"
    CLIENT_RECEIPT_DOWNLOAD = "/receipt/download"
    ENCRYPTED_CREDIT_NOTE = "/credit-note/encrypted"
    EMAIL_RECEIPT = "/receipt/email"
    RECEIPT_DESTINATIONS = "/company/receipt-destinations"

    @staticmethod
    def company_invite_employees(company_id: str) -> str:
        return f"/company/{company_id}/invite/employees"

    @staticmethod
    def company_stores(company_id: str) -> str:
        return f"/company/{company_id}/stores"

    @staticmethod
    def company_store(company_id: str, store_id: str) -> str:
        return f"/company/{company_id}/stores/{store_id}"

    @staticmethod
    def company_store_activate(company_id: str, store_id: str) -> str:
        return f"/company/{company_id}/stores/{store_id}/activate"

    @staticmethod
    def company_store_deactivate(company_id: str, store_id: str) -> str:
        return f"/company/{company_id}/stores/{store_id}/deactivate"

    @staticmethod
    def receipt_destination(destination_id: str) -> str:
        return f"{Endpoints.RECEIPT_DESTINATIONS}/{destination_id}"

    @staticmethod
    def receipt_destination_queue(destination_id: str) -> str:
        return f"{Endpoints.receipt_destination(destination_id)}/receipts/queue"

    @staticmethod
    def receipt_destination_acknowledge(destination_id: str) -> str:
        return f"{Endpoints.receipt_destination_queue(destination_id)}/acknowledge"

    @staticmethod
    def webhook_subscription(subscription_id: str) -> str:
        return f"/webhook/subscription/{subscription_id}"
