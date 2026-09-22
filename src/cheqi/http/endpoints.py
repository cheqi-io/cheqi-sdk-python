"""API endpoint paths for the Cheqi SDK."""

from __future__ import annotations


class Endpoints:
    """Cheqi API endpoint paths."""

    CUSTOMER_MATCH = "/recipient/resolve"
    ENCRYPTED_RECEIPT = "/receipt/encrypted"
    CLIENT_RECEIPT_DOWNLOAD = "/receipt/download"
    ENCRYPTED_CREDIT_NOTE = "/credit-note/encrypted"
    EMAIL_RECEIPT = "/receipt/email"

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
