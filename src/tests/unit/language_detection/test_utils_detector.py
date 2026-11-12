# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import unittest
from unittest.mock import patch

from comps.language_detection.utils import detector

class TestEragTranslationLanguageDetection(unittest.TestCase):
    def test_language_detection(self):
        input_txt = "你好。我做得很好。"
        expected_output = 'zh'

        result = detector.detect_language(input_txt)
        self.assertEqual(result, expected_output)

    def test_language_detection_calls_model_with_single_line_text(self):
        with patch.object(detector, "detect", return_value={"lang": "de", "score": 0.9}) as mock_detect:
            result = detector.detect_language("Hallo.\nWie geht's?")

        mock_detect.assert_called_once_with(text="Hallo. Wie geht's?", low_memory=True)
        self.assertEqual(result, "de")


if __name__ == "__main__":
    unittest.main()
