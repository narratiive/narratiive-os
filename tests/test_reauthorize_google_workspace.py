from __future__ import annotations

import unittest

from scripts.reauthorize_google_workspace import SCOPES, _replace_secret


class GoogleWorkspaceReauthorisationTests(unittest.TestCase):
    def test_minimum_scope_set_adds_compose_without_modify_or_full_mail(self) -> None:
        self.assertIn("https://www.googleapis.com/auth/gmail.compose", SCOPES)
        self.assertIn("https://www.googleapis.com/auth/gmail.readonly", SCOPES)
        self.assertIn("https://www.googleapis.com/auth/gmail.send", SCOPES)
        self.assertNotIn("https://www.googleapis.com/auth/gmail.modify", SCOPES)
        self.assertNotIn("https://mail.google.com/", SCOPES)

    def test_refresh_token_replacement_preserves_other_environment_values(self) -> None:
        result = _replace_secret(
            ["FIRST=value\n", "TONY_GOOGLE_REFRESH_TOKEN=old\n", "LAST=value\n"],
            "TONY_GOOGLE_REFRESH_TOKEN",
            "new-token",
        )
        self.assertEqual(
            result,
            ["FIRST=value\n", "TONY_GOOGLE_REFRESH_TOKEN=new-token\n", "LAST=value\n"],
        )

    def test_refresh_token_is_added_when_missing(self) -> None:
        self.assertEqual(
            _replace_secret(["FIRST=value\n"], "TONY_GOOGLE_REFRESH_TOKEN", "new-token"),
            ["FIRST=value\n", "TONY_GOOGLE_REFRESH_TOKEN=new-token\n"],
        )


if __name__ == "__main__":
    unittest.main()
