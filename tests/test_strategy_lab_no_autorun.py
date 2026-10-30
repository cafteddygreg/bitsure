"""Garde-fou : ouvrir le Strategy Lab ne doit lancer aucun backtest ; les lancements explicites restent."""
import re
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "src" / "components" / "StrategyLabView.tsx").read_text(encoding="utf-8")


class StrategyLabStartup(unittest.TestCase):
    def test_mount_effect_loads_overview_but_never_runs_a_backtest(self):
        blocks = re.findall(r"useEffect\(\(\) => \{(.*?)\}, \[\]\);", SRC, re.S)
        mount = [b for b in blocks if "loadLabOverview()" in b]
        self.assertEqual(len(mount), 1, "effet de montage introuvable")
        self.assertNotIn("executeBacktest(", mount[0])

    def test_no_other_effect_launches_a_backtest(self):
        for effect in re.findall(r"useEffect\(\(\) => \{(.*?)\n  \}, \[", SRC, re.S):
            self.assertNotIn("executeBacktest(", effect)

    def test_explicit_run_buttons_are_still_wired(self):
        self.assertGreaterEqual(len(re.findall(r"onClick=\{\(\) => executeBacktest\(", SRC)), 5)


if __name__ == "__main__":
    unittest.main()
