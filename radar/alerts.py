"""Telegram alerts — the downstream consumer that makes the data real.

Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env; if absent,
alerting degrades gracefully to log messages so the pipeline still runs.
"""

from __future__ import annotations

import logging

import requests

from .models import HealingEvent, Opportunity

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_ITEMS_PER_MESSAGE = 8


class Notifier:
    def __init__(self, bot_token: str, chat_id: str):
        self._token = bot_token
        self._chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    def notify_new_opportunities(self, items: list[Opportunity]) -> None:
        if not items:
            return
        lines = [f"🕸️ {len(items)} new opportunities found:"]
        for item in items[:_MAX_ITEMS_PER_MESSAGE]:
            deadline = f" — deadline {item.deadline}" if item.deadline else ""
            lines.append(f"• [{item.category}] {item.title}{deadline}\n  {item.url}")
        if len(items) > _MAX_ITEMS_PER_MESSAGE:
            lines.append(f"…and {len(items) - _MAX_ITEMS_PER_MESSAGE} more on the dashboard.")
        self._send("\n".join(lines))

    def notify_healing(self, event: HealingEvent) -> None:
        emoji = "✅" if event.outcome == "healed" else "❌"
        self._send(
            f"🕷️ Spider-sense: source '{event.source_id}' broke.\n"
            f"Diagnosis: {event.diagnosis}\n"
            f"{emoji} Outcome: {event.outcome} "
            f"({event.rows_before}→{event.rows_after} rows, "
            f"{event.duration_seconds:.0f}s)"
        )

    def _send(self, text: str) -> None:
        if not self.enabled:
            logger.info("[telegram disabled] %s", text)
            return
        try:
            response = requests.post(
                _API.format(token=self._token),
                json={"chat_id": self._chat_id, "text": text,
                      "disable_web_page_preview": True},
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            # An alerting failure must never kill the pipeline.
            logger.warning("Telegram send failed: %s", exc)
