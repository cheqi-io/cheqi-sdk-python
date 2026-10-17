"""OAuth client-credentials token requests."""

from __future__ import annotations

from typing import Optional

from cheqi.http.client import CheqiApiClient
from cheqi.http.request_options import RequestOptions
from cheqi.models.generated.client_credentials_token_request import ClientCredentialsTokenRequest
from cheqi.models.generated.o_auth_token_exchange_response import OAuthTokenExchangeResponse


class OAuthService:
    """Obtain short-lived Company access tokens with the OAuth client-credentials grant.

    Each token is bound to one Grant, so request one per connected company. The SDK does
    not cache or refresh tokens: store each token with its ``expires_in`` in your own token
    store, request a new one before it expires, and pass it per call with
    ``options=RequestOptions.with_access_token(token)``.
    """

    def __init__(self, api_client: CheqiApiClient) -> None:
        self._api_client = api_client

    def request_access_token(
        self, request: ClientCredentialsTokenRequest, *, options: Optional[RequestOptions] = None,
    ) -> OAuthTokenExchangeResponse:
        """Request an access token for one Grant. ``grant_type`` defaults to ``client_credentials``."""
        return self._api_client.request_access_token(request, options=options)
