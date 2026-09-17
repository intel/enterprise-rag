# Vendored from llm-guard 0.3.16 (https://github.com/protectai/llm-guard) - MIT licence.
# Upstream is archived; this copy is maintained in-tree. See ./LICENSE.
from presidio_analyzer.predefined_recognizers import PhoneRecognizer as PresidioPhoneRecognizer


class PhoneRecognizer(PresidioPhoneRecognizer):
    DEFAULT_SUPPORTED_REGIONS = ("US", "UK", "DE", "FE", "IL", "IN", "CA", "BR", "CN")
