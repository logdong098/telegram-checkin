from __future__ import annotations

import unittest

from telegram_checkin.web import button_action_is_safe, changed_message_texts


class BrowserStateTests(unittest.TestCase):
    def test_returns_only_appended_messages(self) -> None:
        changed = changed_message_texts(
            (("10", "old"),),
            (("10", "old"), ("11", "new response")),
        )

        self.assertEqual(changed, ("new response",))

    def test_returns_edited_message_text(self) -> None:
        changed = changed_message_texts(
            (("10", "pending"),),
            (("10", "签到成功"),),
        )

        self.assertEqual(changed, ("签到成功",))

    def test_ignores_unchanged_conversation(self) -> None:
        changed = changed_message_texts(
            (("10", "same"),),
            (("10", "same"),),
        )

        self.assertEqual(changed, ())

    def test_ignores_older_messages_loaded_by_virtualized_history(self) -> None:
        changed = changed_message_texts(
            (("10", "current menu"),),
            (("8", "old success"), ("10", "current menu"), ("11", "new success")),
        )

        self.assertEqual(changed, ("new success",))

class ButtonSafetyTests(unittest.TestCase):
    def test_allows_plain_callback_or_reply_button(self) -> None:
        self.assertTrue(button_action_is_safe(None, False, "reply-markup-button"))

    def test_rejects_external_and_sensitive_button_classes(self) -> None:
        self.assertFalse(button_action_is_safe("https://example.com", False, None))
        self.assertFalse(button_action_is_safe(None, False, "reply-markup-button is-web-view"))
        self.assertFalse(button_action_is_safe(None, False, "reply-markup-button is-request-phone"))


if __name__ == "__main__":
    unittest.main()
