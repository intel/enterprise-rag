# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Shared implementation for the LLM Guard scanner configuration classes.

The per-guardrail classes stay the entry points: method names, the
`_{input,output,dataprep}_scanners_config` attributes and the scanner builders are
unchanged, so callers and tests are unaffected.
"""

class ScannersConfigBase:
    """Base class for the per-guardrail scanner configuration classes."""

    _SCANNER_KIND = ""

    def _validate_value(self, value):
        """
        Validate and convert the input value.

        Args:
            value (str): The value to be validated and converted.

        Returns:
            bool | int | str: The validated and converted value.
        """
        if value is None:
            return None
        elif value.isdigit():
            return float(value)
        elif value.lower() in ("true", "1", "t", "y", "yes"):
            return True
        elif value.lower() in ("false", "0", "f", "n", "no"):
            return False
        return value

    def _build_scanners_config_from_env(self, scanner_names: list, config_dict: dict) -> dict:
        """Build all scanner configs at once using longest-prefix matching to avoid overlap."""
        all_prefixes = {name: f"{name.upper()}_" for name in scanner_names}
        result = {}
        for scanner_name in scanner_names:
            prefix = all_prefixes[scanner_name]
            longer_prefixes = [p for n, p in all_prefixes.items() if p.startswith(prefix) and n != scanner_name]
            result[scanner_name] = {
                k.removeprefix(prefix).lower(): self._validate_value(v)
                for k, v in config_dict.items()
                if k.startswith(prefix) and not any(k.startswith(lp) for lp in longer_prefixes)
            }
        return result

    def _scanner_config_from_env(self, scanner_name, config_dict):
        """
        Collect a single scanner's configuration out of the environment dictionary.

        Every key prefixed with the scanner's uppercased name is stripped of that prefix,
        lowercased and validated, e.g. `BAN_TOPICS_THRESHOLD` becomes
        `{"ban_topics": {"threshold": ...}}`.

        Args:
            scanner_name (str): The scanner key, e.g. "ban_topics".
            config_dict (dict): The configuration dictionary.

        Returns:
            dict: The scanner configuration, keyed by `scanner_name`.
        """
        prefix = f"{scanner_name.upper()}_"
        return {
            scanner_name: {
                k.removeprefix(prefix).lower(): self._validate_value(v)
                for k, v in config_dict.items() if k.startswith(prefix)
            }
        }

    def _enabled_scanners(self, scanners_config, ignore_non_dict):
        """
        Return the subset of `scanners_config` holding the enabled scanners.

        Args:
            scanners_config (dict): The scanners configuration.
            ignore_non_dict (bool): Skip entries whose value is not a dictionary.

        Returns:
            dict: The enabled scanners' names and configurations.
        """
        return {
            k: v for k, v in scanners_config.items()
            if (not ignore_non_dict or isinstance(v, dict)) and v.get("enabled")
        }

    def _create_enabled_scanners(self, scanners_config, create_scanner, ignore_non_dict=False, **create_kwargs):
        """
        Create the scanners marked as enabled in `scanners_config`.

        A scanner that fails to be created is disabled and its error recorded; the
        remaining scanners are still attempted, and the collected errors are raised
        together once every scanner has been tried.

        Args:
            scanners_config (dict): The scanners configuration. Mutated in place -
                scanners that failed to be created are marked as disabled.
            create_scanner (callable): The subclass' `_create_*_scanner` dispatch method.
            ignore_non_dict (bool): Skip entries whose value is not a dictionary.
            **create_kwargs: Extra keyword arguments forwarded to `create_scanner`.

        Returns:
            list: A list of enabled scanner instances.

        Raises:
            ValueError: If every failure was a validation error.
            Exception: If at least one failure was unexpected.
        """
        enabled_scanners_names_and_configs = self._enabled_scanners(scanners_config, ignore_non_dict)
        enabled_scanners_objects = []

        err_msgs = {} # list for all erronous scanners
        only_validation_errors = True
        for scanner_name, scanner_config in enabled_scanners_names_and_configs.items():
            try:
                self._logger.info(f"Attempting to create scanner: {scanner_name}")
                scanner_object = create_scanner(scanner_name, scanner_config, **create_kwargs)
                enabled_scanners_objects.append(scanner_object)
            except ValueError as e:
                err_msg = f"A ValueError occurred during creating {self._SCANNER_KIND} scanner {scanner_name}: {e}"
                self._logger.error(err_msg)
                err_msgs[scanner_name] = err_msg
                scanners_config[scanner_name]["enabled"] = False
                continue
            except TypeError as e:
                err_msg = f"A TypeError occurred during creating {self._SCANNER_KIND} scanner {scanner_name}: {e}"
                self._logger.error(err_msg)
                err_msgs[scanner_name] = err_msg
                scanners_config[scanner_name]["enabled"] = False
                continue
            except Exception as e:
                err_msg = f"An unexpected error occurred during creating {self._SCANNER_KIND} scanner {scanner_name}: {e}"
                self._logger.error(err_msg)
                err_msgs[scanner_name] = err_msg
                only_validation_errors = False
                scanners_config[scanner_name]["enabled"] = False
                continue

        if err_msgs:
            if only_validation_errors:
                raise ValueError(f"Some scanners failed to be created due to validation errors. The details: {err_msgs}")
            else:
                raise Exception(f"Some scanners failed to be created due to validation or unexpected errors. The details: {err_msgs}")

        return [s for s in enabled_scanners_objects if s is not None]

    def _config_changed(self, scanners_config, new_scanners_config, ignore_non_dict=False):
        """
        Check whether the set of enabled scanners has changed.

        Args:
            scanners_config (dict): The current scanners configuration. Replaced in
                place with `new_scanners_config` when a change is detected.
            new_scanners_config (dict): The incoming scanners configuration.
            ignore_non_dict (bool): Skip entries whose value is not a dictionary.

        Returns:
            bool: True if the configuration has changed, False otherwise.
        """
        del new_scanners_config['id']
        newly_enabled_scanners = {k: {in_k: in_v for in_k, in_v in v.items() if in_k != 'id'}
                                  for k, v in self._enabled_scanners(new_scanners_config, ignore_non_dict).items()}
        previously_enabled_scanners = self._enabled_scanners(scanners_config, ignore_non_dict)
        if newly_enabled_scanners == previously_enabled_scanners: # if the enabled scanners are the same we do nothing
            self._logger.info("No changes in list for enabled scanners. Checking configuration changes...")
            return False
        else:
            self._logger.warning("Scanners configuration has been changed, re-creating scanners")
            scanners_config.clear()
            stripped_new_scanners_config = {k: {in_k: in_v for in_k, in_v in v.items() if in_k != 'id'}
                                            for k, v in new_scanners_config.items()
                                            if not ignore_non_dict or isinstance(v, dict)}
            scanners_config.update(stripped_new_scanners_config)
            return True
