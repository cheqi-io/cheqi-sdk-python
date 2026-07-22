"""Tests for model construction and validation."""

from __future__ import annotations

from decimal import Decimal

from cheqi.config import CheqiSDKConfig, Environment
from cheqi.models.company import Company, CompanyAddress, CreateStoreRequest
from cheqi.models.credit_note import CreditNoteTemplateRequest
from cheqi.models.enums import (
    CardProvider,
    PaymentMethod,
    PaymentType,
    ReceiptFormat,
    ReceiptStatus,
    ReceiverType,
    UnitCode,
)
from cheqi.models.matching import IdentificationDetails, Recipient, RecipientResolutionResponse
from cheqi.models.payment import CardDetails


class TestEnvironment:
    def test_sandbox_url(self) -> None:
        assert Environment.SANDBOX.base_url == "https://sandbox.api.cheqi.io"

    def test_production_url(self) -> None:
        assert Environment.PRODUCTION.base_url == "https://api.cheqi.io"


class TestSDKConfig:
    def test_config_with_environment(self) -> None:
        config = CheqiSDKConfig(
            environment=Environment.SANDBOX,
            api_key="sk_test_123",
        )
        assert config.api_endpoint == "https://sandbox.api.cheqi.io"
        assert config.api_key == "sk_test_123"
        assert config.timeout_seconds == 30
        assert config.max_retries == 3
        assert config.receipt_download_base_url == "https://sandbox.receipt.cheqi.io"

    def test_config_with_custom_endpoint(self) -> None:
        config = CheqiSDKConfig(
            custom_api_endpoint="https://custom.api.example.com",
            api_key="sk_test_123",
        )
        assert config.api_endpoint == "https://custom.api.example.com"
        assert config.receipt_download_base_url is None

    def test_config_requires_endpoint(self) -> None:
        try:
            CheqiSDKConfig(api_key="sk_test_123")
            assert False, "Should have raised"
        except ValueError:
            pass

    def test_config_validates_timeout(self) -> None:
        try:
            CheqiSDKConfig(environment=Environment.SANDBOX, timeout_seconds=0)
            assert False, "Should have raised"
        except ValueError:
            pass

    def test_config_validates_retries(self) -> None:
        try:
            CheqiSDKConfig(environment=Environment.SANDBOX, max_retries=-1)
            assert False, "Should have raised"
        except ValueError:
            pass


class TestEnums:
    def test_payment_method_values(self) -> None:
        assert PaymentMethod.CARD.value == "card"
        assert PaymentMethod.CASH.value == "cash"

    def test_payment_type_values(self) -> None:
        assert PaymentType.CARD_PAYMENT.value == "CARD_PAYMENT"
        assert PaymentType.CARD_PAYMENT.edifact_code == "48"
        assert PaymentType.CASH.value == "CASH"
        assert PaymentType.CASH.edifact_code == "10"

    def test_receipt_status_properties(self) -> None:
        assert ReceiptStatus.DELIVERED.is_final
        assert ReceiptStatus.DELIVERED.is_success
        assert not ReceiptStatus.DELIVERED.is_failure
        assert ReceiptStatus.FAILED.is_failure
        assert not ReceiptStatus.PENDING.is_final

    def test_unit_code_values(self) -> None:
        assert UnitCode.ONE.value == "C62"
        assert UnitCode.KILOGRAM.value == "KGM"
        assert UnitCode.LITER.value == "LTR"

    def test_receipt_format_values(self) -> None:
        assert ReceiptFormat.CHEQI.value == "CHEQI"
        assert ReceiptFormat.UBL_PURCHASE_RECEIPT.value == "UBL_PURCHASE_RECEIPT"

    def test_card_provider_values(self) -> None:
        assert CardProvider.VISA.value == "VISA"
        assert CardProvider.MASTERCARD.value == "MASTERCARD"


class TestRecipient:
    def test_recipient_construction(self) -> None:
        recipient = Recipient(
            id="dev-123",
            receiver_type=ReceiverType.DEVICE,
            public_key="base64key==",
            accepted_formats=[ReceiptFormat.CHEQI],
        )
        assert recipient.id == "dev-123"
        assert recipient.receiver_type == ReceiverType.DEVICE
        assert recipient.accepted_formats == [ReceiptFormat.CHEQI]

    def test_recipient_resolution_response(self) -> None:
        response = RecipientResolutionResponse(
            customer_found=True,
            match_id="match-abc",
            recipients=[
                Recipient(id="dev-1", public_key="key1"),
                Recipient(id="dev-2", public_key="key2"),
            ],
        )
        assert response.customer_found
        assert response.match_id == "match-abc"
        assert len(response.recipients) == 2


class TestIdentificationDetails:
    def test_card_identification(self) -> None:
        details = IdentificationDetails(
            payment_type=PaymentType.CARD_PAYMENT,
            card_details=CardDetails(
                payment_account_reference="PAR123",
                card_provider=CardProvider.VISA,
            ),
        )
        data = details.to_dict()
        assert data["paymentType"] == "CARD_PAYMENT"
        assert data["cardDetails"]["cardProvider"] == "VISA"

    def test_email_identification(self) -> None:
        details = IdentificationDetails(
            payment_type=PaymentType.CARD_PAYMENT,
            recipient_email="customer@example.com",
        )
        data = details.to_dict()
        assert data["recipientEmail"] == "customer@example.com"


class TestCompanyModels:
    def test_company_construction(self) -> None:
        company = Company(
            name="Test Corp",
            legal_name="Test Corporation B.V.",
            tax_number="NL123456789B01",
            address=CompanyAddress(
                street_name="Main Street 1",
                city_name="Amsterdam",
                postal_zone="1012AB",
                country_iso_code="NL",
            ),
        )
        data = company.to_dict()
        assert data["name"] == "Test Corp"
        assert data["address"]["countryIsoCode"] == "NL"

    def test_store_request_uses_current_address_dto_wire_name(self) -> None:
        request = CreateStoreRequest(
            store_name="Amsterdam",
            store_code="AMS",
            address=CompanyAddress(city_name="Amsterdam"),
        )

        assert request.to_dict()["addressDto"] == {"cityName": "Amsterdam"}


class TestCreditNoteModels:
    def test_credit_note_uses_current_subtotal_wire_name(self) -> None:
        request = CreditNoteTemplateRequest(receipt_subtotal="10.00", buyer_country_code="NL")

        assert request.receipt_subtotal == Decimal("10.00")
        assert request.to_dict() == {"creditNoteSubtotal": 10}
