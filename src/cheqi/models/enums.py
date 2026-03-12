"""All enumerations used in the Cheqi SDK."""

from __future__ import annotations

from enum import Enum


class PaymentMethod(str, Enum):
    """Payment methods supported by Cheqi receipts."""

    CARD = "card"
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    DIGITAL_WALLET = "digital_wallet"
    BNPL = "bnpl"
    CRYPTO = "crypto"
    CHECK = "check"
    DIRECT_DEBIT = "direct_debit"
    VOUCHER = "voucher"
    OTHER = "other"


class PaymentType(str, Enum):
    """Payment type codes (UN/EDIFACT 4461).

    Values are enum names (matching Java SDK Jackson serialization).
    Use .edifact_code for the numeric EDIFACT code.
    """

    CARD_PAYMENT = "CARD_PAYMENT"
    DIRECT_DEBIT = "DIRECT_DEBIT"
    CASH = "CASH"

    @property
    def edifact_code(self) -> str:
        """Return the UN/EDIFACT 4461 code."""
        return _PAYMENT_TYPE_CODES[self]


_PAYMENT_TYPE_CODES = {
    PaymentType.CARD_PAYMENT: "48",
    PaymentType.DIRECT_DEBIT: "49",
    PaymentType.CASH: "10",
}


class CardProvider(str, Enum):
    """Supported card providers."""

    MAESTRO = "MAESTRO"
    MASTERCARD = "MASTERCARD"
    VISA = "VISA"
    AMERICAN_EXPRESS = "AMERICAN_EXPRESS"


class ReceiptStatus(str, Enum):
    """Receipt lifecycle status."""

    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

    @property
    def is_final(self) -> bool:
        return self in (ReceiptStatus.DELIVERED, ReceiptStatus.CANCELLED, ReceiptStatus.REFUNDED)

    @property
    def is_failure(self) -> bool:
        return self == ReceiptStatus.FAILED

    @property
    def is_success(self) -> bool:
        return self in (ReceiptStatus.SENT, ReceiptStatus.DELIVERED)


class ReceiptFormat(str, Enum):
    """Supported receipt formats."""

    CHEQI = "CHEQI"
    UBL_XML = "UBL_XML"


class ReceiverType(str, Enum):
    """Types of receipt receivers."""

    WEBHOOK = "WEBHOOK"
    DEVICE = "DEVICE"
    CLIENT_APPLICATION = "CLIENT_APPLICATION"
    COMPANY = "COMPANY"


class RecipientEntityType(str, Enum):
    """Recipient entity types for VAT determination."""

    BUSINESS = "BUSINESS"
    CONSUMER = "CONSUMER"


class VatRegime(str, Enum):
    """VAT regime classification."""

    DOMESTIC = "DOMESTIC"
    DOMESTIC_NO_VAT = "DOMESTIC_NO_VAT"
    REVERSE_CHARGE_EU = "REVERSE_CHARGE_EU"
    REVERSE_CHARGE_NON_EU = "REVERSE_CHARGE_NON_EU"
    INTRA_EU_VAT_CHARGED = "INTRA_EU_VAT_CHARGED"
    EXPORT = "EXPORT"
    FOREIGN_VAT = "FOREIGN_VAT"
    TAX_EXEMPT = "TAX_EXEMPT"


class AccountIdentifierType(str, Enum):
    """Payment account identifier types."""

    IBAN = "IBAN"


class BarcodeType(str, Enum):
    """Supported barcode and scannable code types."""

    QR_CODE = "QR_CODE"
    EAN_13 = "EAN_13"
    EAN_8 = "EAN_8"
    CODE_128 = "CODE_128"
    UPC_A = "UPC_A"
    DATA_MATRIX = "DATA_MATRIX"


class KeyAlgorithm(str, Enum):
    """Cryptographic key algorithms."""

    RSA = "RSA"
    RSA_2048 = "RSA_2048"
    RSA_4096 = "RSA_4096"
    ECDSA_P256 = "ECDSA_P256"
    ECDSA_P384 = "ECDSA_P384"
    ED25519 = "ED25519"


class UnitCode(str, Enum):
    """Unit of measure codes based on UN/ECE Recommendation 20.

    The enum value is the UN/ECE code string (e.g., "C62" for ONE).
    """

    # Most common
    ONE = "C62"
    EACH = "EA"

    # Weight
    KILOGRAM = "KGM"
    GRAM = "GRM"
    MILLIGRAM = "MGM"
    TONNE = "TNE"
    POUND = "LBR"
    OUNCE = "ONZ"

    # Volume
    LITER = "LTR"
    MILLILITER = "MLT"
    CENTILITER = "CLT"
    HECTOLITER = "HLT"
    CUBIC_METER = "MTQ"
    CUBIC_CENTIMETER = "CMQ"
    GALLON_US = "GLL"
    GALLON_UK = "GLI"

    # Length
    METER = "MTR"
    CENTIMETER = "CMT"
    MILLIMETER = "MMT"
    KILOMETER = "KMT"
    INCH = "INH"
    FOOT = "FOT"
    YARD = "YRD"
    MILE = "SMI"

    # Area
    SQUARE_METER = "MTK"
    SQUARE_CENTIMETER = "CMK"
    SQUARE_FOOT = "FTK"
    SQUARE_INCH = "INK"

    # Time
    SECOND = "SEC"
    MINUTE = "MIN"
    HOUR = "HUR"
    DAY = "DAY"
    WEEK = "WEE"
    MONTH = "MON"
    YEAR = "ANN"

    # Packaging
    SET = "SET"
    PAIR = "PR"
    DOZEN = "DZN"
    PIECE = "NMP"
    PACK = "XPK"
    BOX = "BX"
    CARTON = "CT"
    CASE = "CS"
    PACKAGE = "PK"
    PALLET = "PF"
    BOTTLE = "BO"
    CAN = "CA"
    BAG = "BG"

    # Service/Activity
    SERVICE_UNIT = "E48"
    ACTIVITY = "ACT"
    JOB = "E51"

    # Information/Data
    BYTE = "AD"
    KILOBYTE = "2P"
    MEGABYTE = "4L"


class ReturnCondition(str, Enum):
    """Condition of returned items."""

    DEFECTIVE = "DEFECTIVE"
    DAMAGED = "DAMAGED"
    WRONG_ITEM = "WRONG_ITEM"
    NOT_AS_DESCRIBED = "NOT_AS_DESCRIBED"
    UNWANTED = "UNWANTED"
    EXPIRED = "EXPIRED"
    INCOMPLETE = "INCOMPLETE"


class RefundPreference(str, Enum):
    """Customer's preferred refund method."""

    ORIGINAL_PAYMENT_METHOD = "ORIGINAL_PAYMENT_METHOD"
    BANK_TRANSFER = "BANK_TRANSFER"
    STORE_CREDIT = "STORE_CREDIT"
