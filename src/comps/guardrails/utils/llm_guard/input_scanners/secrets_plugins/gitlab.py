# Vendored from llm-guard 0.3.16 (https://github.com/protectai/llm-guard) - MIT licence.
# Upstream is archived; this copy is maintained in-tree. See ./LICENSE.
"""
This plugin searches for GitLab secrets.
"""

import re

from detect_secrets.plugins.base import RegexBasedDetector


class GitLabDetector(RegexBasedDetector):
    """Scans for GitLab Secrets."""

    @property
    def secret_type(self) -> str:
        return "GitLab Secret"

    @property
    def denylist(self) -> list[re.Pattern]:
        return [
            # GitLab Personal Access Token
            re.compile(r"""glpat-[0-9a-zA-Z\-\_]{20}"""),
            # GitLab Pipeline Trigger Token
            re.compile(r"""glptt-[0-9a-f]{40}"""),
            # GitLab Runner Registration Token
            re.compile(r"""GR1348941[0-9a-zA-Z\-\_]{20}"""),
        ]
