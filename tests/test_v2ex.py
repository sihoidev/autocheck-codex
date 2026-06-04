from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from v2ex import mission_is_completed, parse_redeem_path


class V2EXParsingTest(unittest.TestCase):
    def test_parse_redeem_path_from_onclick(self) -> None:
        html = """
        <input type="button" value="领取 10 铜币"
            onclick="location.href = '/mission/daily/redeem?once=48881';" />
        """

        self.assertEqual(parse_redeem_path(html), "/mission/daily/redeem?once=48881")

    def test_parse_redeem_path_from_absolute_href(self) -> None:
        html = '<a href="https://www.v2ex.com/mission/daily/redeem?once=12345">领取</a>'

        self.assertEqual(parse_redeem_path(html), "/mission/daily/redeem?once=12345")

    def test_mission_is_completed_from_balance_button(self) -> None:
        html = """
        <div class="cell">
          <h1>每日登录奖励 20260604</h1>
          <input type="button" value="查看我的账户余额" onclick="location.href = '/balance';" />
        </div>
        """

        self.assertTrue(mission_is_completed(html))

    def test_mission_is_completed_from_text_status(self) -> None:
        html = "<div>每日登录奖励已领取，可以查看账户余额。</div>"

        self.assertTrue(mission_is_completed(html))


if __name__ == "__main__":
    unittest.main()
