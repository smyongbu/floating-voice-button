import unittest

from global_hotkey import MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT, parse_hotkey


class GlobalHotkeyTests(unittest.TestCase):
    def test_default_hotkey_is_canonical_and_non_repeating(self):
        parsed = parse_hotkey("control + alt + space")
        self.assertEqual(parsed.label, "Ctrl+Alt+Space")
        self.assertEqual(
            parsed.modifiers,
            MOD_CONTROL | MOD_ALT | MOD_NOREPEAT,
        )
        self.assertEqual(parsed.virtual_key, 0x20)

    def test_letters_function_keys_and_shift_are_supported(self):
        letter = parse_hotkey("Alt+Shift+k")
        function = parse_hotkey("Ctrl+F12")
        standalone_function = parse_hotkey("f8")
        self.assertEqual(letter.label, "Alt+Shift+K")
        self.assertEqual(letter.modifiers, MOD_ALT | MOD_SHIFT | MOD_NOREPEAT)
        self.assertEqual(function.label, "Ctrl+F12")
        self.assertEqual(function.virtual_key, 0x7B)
        self.assertEqual(standalone_function.label, "F8")
        self.assertEqual(standalone_function.modifiers, MOD_NOREPEAT)

    def test_plain_or_modifier_only_hotkeys_are_rejected(self):
        for value in ("A", "Shift+A", "Ctrl+Alt", "Ctrl+Alt+Unknown"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_hotkey(value)


if __name__ == "__main__":
    unittest.main()
