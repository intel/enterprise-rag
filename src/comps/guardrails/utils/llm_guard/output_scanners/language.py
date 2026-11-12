# Vendored from llm-guard 0.3.16 (https://github.com/protectai/llm-guard) - MIT licence.
# Upstream is archived; this copy is maintained in-tree. See ./LICENSE.
from __future__ import annotations

from ..input_scanners.language import Language as InputLanguage, MatchType
from ..model import Model

from .base import Scanner


class Language(Scanner):
    """
    Language scanner is responsible for determining the language of a given text
    prompt and verifying its validity against a list of predefined languages.
    """

    def __init__(
        self,
        valid_languages: list[str],
        *,
        model: Model | None = None,
        threshold: float = 0.7,
        match_type: MatchType | str = MatchType.FULL,
    ) -> None:
        """
        Initializes the Language scanner with a list of valid languages.

        Parameters:
            model (Model, optional): A Model object containing the path to the model.
            valid_languages (Sequence[str]): A list of valid language codes.
            threshold (float): Minimum confidence score.
            match_type (MatchType): Whether to match the full text or individual sentences. Default is MatchType.FULL.
        """

        self._scanner = InputLanguage(
            valid_languages,
            model=model,
            threshold=threshold,
            match_type=match_type,
        )

    def scan(self, prompt: str, output: str) -> tuple[str, bool, float]:
        return self._scanner.scan(output)
