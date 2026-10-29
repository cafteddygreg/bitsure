"""Garde-fou i18n : la table FR<->EN des messages serveur (src/serverMessages.ts) reste cohérente."""
import json
import re
import unittest
from pathlib import Path

TABLE = Path(__file__).resolve().parent.parent / "src" / "serverMessages.ts"


def _pairs():
    out = []
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        line = line.strip().rstrip(",")
        if line.startswith('["') and line.endswith("]"):
            out.append(json.loads(line))
    return out


class ServerMessagesTable(unittest.TestCase):
    def test_pairs_are_well_formed_and_placeholders_match(self):
        pairs = _pairs()
        self.assertGreater(len(pairs), 200)
        for fr, en in pairs:
            self.assertTrue(fr.strip() and en.strip(), (fr, en))
            self.assertEqual(fr.count("{}"), en.count("{}"), f"placeholders différents : {fr!r} / {en!r}")

    def test_no_duplicate_source_messages(self):
        frs = [p[0] for p in _pairs()]
        self.assertEqual(len(frs), len(set(frs)))

    def test_english_side_is_not_french(self):
        accents = re.compile(r"[éèêàùçôîï]")
        bad = [en for _, en in _pairs() if accents.search(en)]
        self.assertEqual(bad, [])


class TelegramI18nParity(unittest.TestCase):
    def test_fr_en_keys_match(self):
        import i18n  # i18n.py (bot Telegram)

        texts = i18n.TEXTS
        only_fr = sorted(set(texts["fr"]) - set(texts["en"]))
        only_en = sorted(set(texts["en"]) - set(texts["fr"]))
        self.assertEqual(only_fr, [], f"clés absentes en anglais : {only_fr[:10]}")
        self.assertEqual(only_en, [], f"clés absentes en français : {only_en[:10]}")


if __name__ == "__main__":
    unittest.main()
