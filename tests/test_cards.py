"""Tests for card update behavior.

The request-body construction in ``FavroClient.update_card`` is exercised
against a fake ``_put`` so no live Favro access is needed.
"""

from __future__ import annotations

from typing import Any

from favro_mcp.api.client import FavroClient


def _client_capturing_put() -> tuple[FavroClient, dict[str, Any]]:
    """A client whose ``_put`` records the body and returns a minimal card."""
    captured: dict[str, Any] = {}

    def fake_put(path: str, data: dict[str, Any]) -> dict[str, Any]:
        captured["path"] = path
        captured["data"] = data
        return {
            "cardId": "card-1",
            "organizationId": "org-1",
            "cardCommonId": "common-1",
            "name": "Card",
            "sequentialId": 1,
        }

    client = FavroClient("e@example.com", "token")
    client._put = fake_put  # type: ignore[method-assign]
    return client, captured


def test_update_card_sends_parent_card_id() -> None:
    client, captured = _client_capturing_put()
    client.update_card(card_id="card-1", parent_card_id="parent-board-card-id")
    assert captured["path"] == "/cards/card-1"
    assert captured["data"]["parentCardId"] == "parent-board-card-id"


def test_update_card_omits_parent_when_not_set() -> None:
    client, captured = _client_capturing_put()
    client.update_card(card_id="card-1", name="Renamed")
    assert "parentCardId" not in captured["data"]
    assert captured["data"]["name"] == "Renamed"
