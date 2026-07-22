"""Main entry point for the Cheqi SDK."""

from __future__ import annotations

from typing import Optional

from cheqi.config import CheqiSDKConfig, Environment
from cheqi.http.client import DefaultCheqiApiClient
from cheqi.models.encryption import EncryptedReceipt
from cheqi.services.company import CompanyService
from cheqi.services.credit_note import CreditNoteService
from cheqi.services.decryption import DecryptedReceipt, DecryptionService
from cheqi.services.download import DownloadService
from cheqi.services.encryption import EncryptionService
from cheqi.services.matching import MatchingService
from cheqi.services.receipt import ReceiptService
from cheqi.services.receipt_processor import ReceiptProcessor
from cheqi.services.store import StoreService
from cheqi.services.verification import VerificationService


class CheqiSDK:
    """Main entry point for the Cheqi SDK providing end-to-end encrypted receipt processing.

    Example usage::

        sdk = CheqiSDK(
            environment=Environment.PRODUCTION,
            api_key="sk_live_...",
        )

        # Process a receipt
        result = sdk.receipt_service.process_complete_receipt(
            identification_details, receipt_request, access_token
        )
    """

    def __init__(
        self,
        *,
        environment: Optional[Environment] = None,
        custom_api_endpoint: Optional[str] = None,
        receipt_download_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        private_key: Optional[str] = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
    ) -> None:
        self._config = CheqiSDKConfig(
            environment=environment,
            custom_api_endpoint=custom_api_endpoint,
            receipt_download_base_url=receipt_download_base_url,
            api_key=api_key,
            private_key=private_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

        self._verification_service = VerificationService()
        self._decryption_service = DecryptionService()
        self._receipt_processor = ReceiptProcessor()
        self._download_service = DownloadService()
        self._encryption_service = EncryptionService()
        self._api_client = DefaultCheqiApiClient(self._config)
        self._matching_service = MatchingService(self._api_client)
        self._receipt_service = ReceiptService(
            self._api_client,
            self._encryption_service,
            self._matching_service,
            self._download_service,
            self._config.receipt_download_base_url,
        )
        self._company_service = CompanyService(self._api_client)
        self._store_service = StoreService(self._api_client)
        self._credit_note_service = CreditNoteService(
            self._api_client, self._encryption_service, self._matching_service
        )

    @property
    def config(self) -> CheqiSDKConfig:
        return self._config

    @property
    def encryption_service(self) -> EncryptionService:
        return self._encryption_service

    @property
    def decryption_service(self) -> DecryptionService:
        return self._decryption_service

    @property
    def matching_service(self) -> MatchingService:
        return self._matching_service

    @property
    def download_service(self) -> DownloadService:
        return self._download_service

    @property
    def receipt_service(self) -> ReceiptService:
        return self._receipt_service

    @property
    def credit_note_service(self) -> CreditNoteService:
        return self._credit_note_service

    @property
    def company_service(self) -> CompanyService:
        return self._company_service

    @property
    def store_service(self) -> StoreService:
        return self._store_service

    @property
    def verification_service(self) -> VerificationService:
        return self._verification_service

    @property
    def api_client(self) -> DefaultCheqiApiClient:
        return self._api_client

    def process_encrypted_receipt(
        self, encrypted_receipt: EncryptedReceipt, private_key: str
    ) -> DecryptedReceipt:
        """Decrypt a receipt and merge its recipient context into every format."""
        decrypted = self._decryption_service.decrypt_receipt(encrypted_receipt, private_key)
        return self._receipt_processor.merge(decrypted)

    def close(self) -> None:
        """Close the SDK and release resources."""
        self._api_client.close()

    def __enter__(self) -> CheqiSDK:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
