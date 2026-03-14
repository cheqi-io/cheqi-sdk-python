from cheqi.services.verification import VerificationService


class TestXmlVerification:
    def test_canonicalize_and_hash_xml_ignores_formatting_whitespace(self) -> None:
        service = VerificationService()
        compact_xml = (
            "<Invoice><AccountingCustomerParty><Party><Name>Cheqi</Name></Party>"
            "</AccountingCustomerParty></Invoice>"
        )
        formatted_xml = """
            <Invoice>
              <AccountingCustomerParty>
                <Party>
                  <Name>Cheqi</Name>
                </Party>
              </AccountingCustomerParty>
            </Invoice>
        """

        assert service.canonicalize_and_hash_xml(compact_xml) == service.canonicalize_and_hash_xml(
            formatted_xml
        )

    def test_canonicalize_and_hash_xml_preserves_meaningful_text_whitespace(self) -> None:
        service = VerificationService()
        single_spaced = "<Invoice><Name>Cheqi BV</Name></Invoice>"
        double_spaced = "<Invoice><Name>Cheqi  BV</Name></Invoice>"

        assert service.canonicalize_and_hash_xml(single_spaced) != service.canonicalize_and_hash_xml(
            double_spaced
        )
