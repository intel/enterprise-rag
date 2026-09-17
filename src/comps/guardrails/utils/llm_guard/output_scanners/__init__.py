# Vendored from llm-guard 0.3.16 (https://github.com/protectai/llm-guard) - MIT licence.
# Upstream is archived; this copy is maintained in-tree. See ./LICENSE.

from importlib import import_module

_EXPORTS = {
    "BanCode": ".ban_code",
    "BanCompetitors": ".ban_competitors",
    "BanSubstrings": ".ban_substrings",
    "BanTopics": ".ban_topics",
    "Bias": ".bias",
    "Code": ".code",
    "Deanonymize": ".deanonymize",
    "FactualConsistency": ".factual_consistency",
    "Gibberish": ".gibberish",
    "JSON": ".json",
    "Language": ".language",
    "LanguageSame": ".language_same",
    "MaliciousURLs": ".malicious_urls",
    "NoRefusal": ".no_refusal",
    "NoRefusalLight": ".no_refusal",
    "ReadingTime": ".reading_time",
    "Regex": ".regex",
    "Relevance": ".relevance",
    "Sensitive": ".sensitive",
    "Sentiment": ".sentiment",
    "Toxicity": ".toxicity",
    "URLReachability": ".url_reachabitlity",
    "get_scanner_by_name": ".util",
}

__all__ = [
    "BanCode",
    "BanCompetitors",
    "BanSubstrings",
    "BanTopics",
    "Bias",
    "Code",
    "Deanonymize",
    "JSON",
    "Language",
    "LanguageSame",
    "MaliciousURLs",
    "NoRefusal",
    "NoRefusalLight",
    "ReadingTime",
    "FactualConsistency",
    "Gibberish",
    "Regex",
    "Relevance",
    "Sensitive",
    "Sentiment",
    "Toxicity",
    "URLReachability",
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
