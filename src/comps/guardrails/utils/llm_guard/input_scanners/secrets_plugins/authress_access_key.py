# Vendored from llm-guard 0.3.16 (https://github.com/protectai/llm-guard) - MIT licence.
# Upstream is archived; this copy is maintained in-tree. See ./LICENSE.
"""
This plugin searches for Authress Service Client Access Keys
"""

import re

from detect_secrets.plugins.base import RegexBasedDetector


class AuthressAccessKeyDetector(RegexBasedDetector):
    """Scans for Authress Service Client Access Keys."""

    @property
    def secret_type(self) -> str:
        return "Authress Service Client Access Key"

    @property
    def denylist(self) -> list[re.Pattern]:
        return [
            # For Authress Service Client Access Key
            re.compile(
                r"""(?i)\b((?:sc|ext|scauth|authress)_[a-z0-9]{5,30}\.[a-z0-9]{4,6}\.acc[_-][a-z0-9-]{10,32}\.[a-z0-9+/_=-]{30,120})(?:['|\"|\n|\r|\s|\x60|;]|$)"""
            ),
        ]
