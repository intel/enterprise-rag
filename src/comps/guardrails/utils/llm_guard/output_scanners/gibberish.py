# Vendored from llm-guard 0.3.16 (https://github.com/protectai/llm-guard) - MIT licence.
# Upstream is archived; this copy is maintained in-tree. See ./LICENSE.
from __future__ import annotations

from ..input_scanners.gibberish import Gibberish as InputGibberish, MatchType
from ..model import Model

from .base import Scanner


class Gibberish(Scanner):
    """
    A scanner that detects gibberish text.
    """

    def __init__(
        self,
        *,
        model: Model | None = None,
        threshold: float = 0.7,
        match_type: MatchType | str = MatchType.FULL,
    ) -> None:
        """
        Initializes the Gibberish scanner with a probability threshold for gibberish detection.

        Parameters:
           model (Model, optional): The model used.
           threshold (float): The probability threshold for gibberish detection. Default is 0.7.
           match_type (MatchType): Whether to match the full text or individual sentences. Default is MatchType.FULL.
        """

        self._scanner = InputGibberish(
            model=model,
            threshold=threshold,
            match_type=match_type,
        )

    def scan(self, prompt: str, output: str) -> tuple[str, bool, float]:
        return self._scanner.scan(output)
