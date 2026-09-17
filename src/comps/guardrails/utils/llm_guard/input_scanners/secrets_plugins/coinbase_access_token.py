# Vendored from llm-guard 0.3.16 (https://github.com/protectai/llm-guard) - MIT licence.
# Upstream is archived; this copy is maintained in-tree. See ./LICENSE.
"""
This plugin searches for Coinbase Access Token
"""

import re

from detect_secrets.plugins.base import RegexBasedDetector


class CoinbaseAccessTokenDetector(RegexBasedDetector):
    """Scans for Coinbase Access Token."""

    @property
    def secret_type(self) -> str:
        return "Coinbase Access Token"

    @property
    def denylist(self) -> list[re.Pattern]:
        return [
            # For Coinbase Access Token
            re.compile(
                r"""(?i)(?:coinbase)(?:[0-9a-z\-_\t .]{0,20})(?:[\s|']|[\s|"]){0,3}(?:=|>|:{1,3}=|\|\|:|<=|=>|:|\?=)(?:'|\"|\s|=|\x60){0,5}([a-z0-9_-]{64})(?:['|\"|\n|\r|\s|\x60|;]|$)"""
            ),
        ]
