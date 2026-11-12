# Vendored from llm-guard 0.3.16 (https://github.com/protectai/llm-guard) - MIT licence.
# Upstream is archived; this copy is maintained in-tree. See ./LICENSE.
from __future__ import annotations

from typing import Literal, get_args

from .model import Model
from .util import get_logger, lazy_load_dep, model_dtype

LOGGER = get_logger()


def get_tokenizer(model: Model):
    """
    This function loads a tokenizer given a model identifier and caches it.
    Subsequent calls with the same model_identifier will return the cached tokenizer.

    Args:
        model (Model): The model to load the tokenizer for.
    """
    transformers = lazy_load_dep("transformers")
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        model.path, revision=model.revision, **model.tokenizer_kwargs
    )
    return tokenizer


def get_tokenizer_and_model_for_classification(
    model: Model,
):
    """
    This function loads a tokenizer and model given a model identifier and caches them.
    Subsequent calls with the same model_identifier will return the cached tokenizer.

    Args:
        model (str): The model identifier to load the tokenizer and model for.
    """
    tf_tokenizer = get_tokenizer(model)
    transformers = lazy_load_dep("transformers")

    tf_model = transformers.AutoModelForSequenceClassification.from_pretrained(
        model.path,
        subfolder=model.subfolder,
        revision=model.revision,
        dtype=model_dtype(),
        **model.kwargs,
    )
    LOGGER.debug("Initialized classification model", model=model)

    return tf_tokenizer, tf_model


def get_tokenizer_and_model_for_ner(
    model: Model,
):
    """
    This function loads a tokenizer and model given a model identifier and caches them.
    Subsequent calls with the same model_identifier will return the cached tokenizer.

    Args:
        model (str): The model identifier to load the tokenizer and model for.
    """
    tf_tokenizer = get_tokenizer(model)
    transformers = lazy_load_dep("transformers")

    tf_model = transformers.AutoModelForTokenClassification.from_pretrained(
        model.path,
        subfolder=model.subfolder,
        revision=model.revision,
        dtype=model_dtype(),
        **model.kwargs,
    )
    LOGGER.debug("Initialized NER model", model=model)

    return tf_tokenizer, tf_model


ClassificationTask = Literal["text-classification", "zero-shot-classification"]


def pipeline(
    task: str,
    model,
    tokenizer,
    **kwargs,
):
    if task not in get_args(ClassificationTask):
        raise ValueError(f"Invalid task. Must be one of {ClassificationTask}")

    if kwargs.get("max_length", None) is None:
        kwargs["max_length"] = tokenizer.model_max_length

    transformers = lazy_load_dep("transformers")
    return transformers.pipeline(
        task,
        model=model,
        tokenizer=tokenizer,
        **kwargs,
    )
