from __future__ import annotations

import unittest

from anchor.application.memory.provider_service import redact_sensitive_text


class MemoryProviderSecurityTest(unittest.TestCase):
    def test_redacts_secrets_and_personal_identifiers(self) -> None:
        text = "token=sk-or-v1-1234567890abcdef email user@example.com phone +7 999 123-45-67"

        redacted = redact_sensitive_text(text)

        self.assertNotIn("sk-or-v1-1234567890abcdef", redacted)
        self.assertNotIn("user@example.com", redacted)
        self.assertNotIn("+7 999 123-45-67", redacted)
        self.assertIn("[REDACTED_SECRET]", redacted)
        self.assertIn("[REDACTED_EMAIL]", redacted)
        self.assertIn("[REDACTED_PHONE]", redacted)
