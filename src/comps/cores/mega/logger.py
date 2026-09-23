# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os


def get_erag_logger(name: str = "erag", log_level: str = "INFO"):
    """Get or create a logger with ERAG configuration.

    Returns a configured logger instance. If the logger already exists,
    updates its log level and returns it. Handler configuration is only
    applied to new loggers.

    :param name: Logger name (typically the service or component name)
    :param log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    :return: Configured logger instance
    """
    logger = logging.getLogger(name)

    # Always apply log level (even for existing loggers)
    logger.setLevel(log_level)

    # Only configure handler if this is a new logger (no handlers yet)
    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="[%(asctime)-15s] [%(levelname)8s] - [%(name)s] - %(message)s"
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Set propagation behavior
        if os.environ.get('LOGGING_PROPAGATE', 'false').lower() == 'true':
            logger.propagate = True
        else:
            logger.propagate = False

    return logger


def change_erag_logger_level(logger, log_level) -> None:
    """Change the log level of an existing logger.

    :param logger: Logger instance to modify
    :param log_level: New log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logger.setLevel(log_level)
