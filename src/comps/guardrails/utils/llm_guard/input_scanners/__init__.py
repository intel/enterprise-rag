# Vendored from llm-guard 0.3.16 (https://github.com/protectai/llm-guard) - MIT licence.
# Upstream is archived; this copy is maintained in-tree. See ./LICENSE.
from importlib import import_module

_EXPORTS = {
    "Anonymize": ".anonymize",
    "BanCode": ".ban_code",
    "BanCompetitors": ".ban_competitors",
    "BanSubstrings": ".ban_substrings",
    "BanTopics": ".ban_topics",
    "Code": ".code",
    "Gibberish": ".gibberish",
    "InvisibleText": ".invisible_text",
    "Language": ".language",
    "PromptInjection": ".prompt_injection",
    "Regex": ".regex",
    "Secrets": ".secrets",
    "Sentiment": ".sentiment",
    "TokenLimit": ".token_limit",
    "Toxicity": ".toxicity",
    "get_scanner_by_name": ".util",
}

__all__ = [
    "Anonymize",
    "BanCode",
    "BanCompetitors",
    "BanSubstrings",
    "BanTopics",
    "Code",
    "Gibberish",
    "InvisibleText",
    "Language",
    "PromptInjection",
    "Regex",
    "Secrets",
    "Sentiment",
    "TokenLimit",
    "Toxicity",
    "get_scanner_by_name",
]


def __getattr__(name: str):
    """Import the module backing ``name`` on first access (PEP 562)."""
    try:
        module = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    value = getattr(import_module(module, __name__), name)
    globals()[name] = value  # cache so __getattr__ is not consulted again
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
