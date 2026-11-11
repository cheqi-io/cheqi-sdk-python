import json
import traceback

import httpx
import pytest

from cheqi.config import CheqiSDKConfig, Environment
from cheqi.exceptions import CheqiApiError
from cheqi.http.client import DefaultCheqiApiClient
from cheqi.models.generated.authorization_code_exchange_request import AuthorizationCodeExchangeRequest
from cheqi.models.generated.client_application_public_key_request import ClientApplicationPublicKeyRequest
from cheqi.models.generated.client_credentials_token_request import ClientCredentialsTokenRequest
from cheqi.models.generated.o_auth_token_exchange_response import OAuthTokenExchangeResponse


@pytest.mark.parametrize("model,field", [
    (ClientCredentialsTokenRequest, "client_secret"),
    (ClientApplicationPublicKeyRequest, "client_secret"),
    (AuthorizationCodeExchangeRequest, "client_secret"),
    (AuthorizationCodeExchangeRequest, "code"),
    (AuthorizationCodeExchangeRequest, "code_verifier"),
    (OAuthTokenExchangeResponse, "access_token"),
])
def test_credentials_redact_diagnostics_but_preserve_wire_json(model: type, field: str) -> None:
    secret = "dummy-secret\nsecond-line"
    fields = {field: secret}
    if model is ClientApplicationPublicKeyRequest:
        fields.update(publicKey="public", keyAlgorithm="RSA_2048", client_id="client")
    value = model(**fields)
    for diagnostic in (str(value), repr(value), value.to_str()):
        assert "dummy-secret" not in diagnostic
        assert "second-line" not in diagnostic
    assert json.loads(value.to_json())[field] == secret
    assert getattr(value, field) == secret


@pytest.mark.parametrize("status,body", [
    (400, '{"message":"dummy-echoed-secret"}'),
    (200, '{"access_token":"dummy-echoed-secret","expires_in":"dummy-echoed-secret"}'),
    (200, '{"access_token":"dummy-echoed-secret"'),
])
def test_token_errors_do_not_expose_response_or_validation_input(status: int, body: str) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, text=body))) as http:
        client = DefaultCheqiApiClient(CheqiSDKConfig(environment=Environment.SANDBOX), http_client=http)
        with pytest.raises(CheqiApiError) as caught:
            client.request_access_token(ClientCredentialsTokenRequest(
                client_id="client", client_secret="secret", grant_id="grant",
            ))
        error = caught.value
        assert "dummy-echoed-secret" not in "".join(traceback.format_exception(type(error), error, error.__traceback__))
