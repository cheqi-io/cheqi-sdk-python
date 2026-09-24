from __future__ import annotations

import logging

import pytest

from cheqi.config import CheqiSDKConfig, Environment


def test_api_key_does_not_require_legacy_prefix(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="cheqi.config"):
        config = CheqiSDKConfig(environment=Environment.SANDBOX, api_key="example_api_key")

    assert config.api_key == "example_api_key"
    assert not caplog.records
