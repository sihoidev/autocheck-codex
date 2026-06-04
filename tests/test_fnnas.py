from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fnnas import parse_sign_data


class FNNASParsingTest(unittest.TestCase):
    def test_parse_plain_multiline_sign_data(self) -> None:
        value = "salt\nAUTH%2Fvalue\nSIGN123"

        self.assertEqual(parse_sign_data(value), ("salt", "AUTH%2Fvalue", "SIGN123"))

    def test_parse_key_value_multiline_sign_data(self) -> None:
        value = """
        fn_pvRK_2132_saltkey=salt
        fn_pvRK_2132_auth=AUTH%2Fvalue
        fn_pvRK_2132_sign=SIGN123
        """

        self.assertEqual(parse_sign_data(value), ("salt", "AUTH%2Fvalue", "SIGN123"))


if __name__ == "__main__":
    unittest.main()
