# Vendored from llm-guard 0.3.16 (https://github.com/protectai/llm-guard) - MIT licence.
# Upstream is archived; this copy is maintained in-tree. See ./LICENSE.
"""
This plugin searches for Flutterwave API keys.
"""

import re

from detect_secrets.plugins.base import RegexBasedDetector


class FlutterwaveDetector(RegexBasedDetector):
    """Scans for Flutterwave API Keys."""

    @property
    def secret_type(self) -> str:
        return "Flutterwave API Key"

    @property
    def denylist(self) -> list[re.Pattern]:
        return [
            # Flutterwave Encryption Key
            re.compile(r"""(?i)FLWSECK_TEST-[a-h0-9]{12}"""),
            # Flutterwave Public Key
            re.compile(r"""(?i)FLWPUBK_TEST-[a-h0-9]{32}-X"""),
            # Flutterwave Secret Key
            re.compile(r"""(?i)FLWSECK_TEST-[a-h0-9]{32}-X"""),
        ]
