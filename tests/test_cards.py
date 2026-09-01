"""Tests for card update behavior.

The request-body construction in ``FavroClient.update_card`` is exercised
against a fake ``_put`` so no live Favro access is needed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest
from fastmcp import Context

from favro_mcp.api.client import FavroClient
from favro_mcp.api.models import Card, Widget
from favro_mcp.tools import cards as card_tools
from favro_mcp.tools.cards import _card_to_dict


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


def test_add_card_dependencies_posts_dependencies_body() -> None:
    captured: dict[str, Any] = {}

    def fake_post(path: str, data: dict[str, Any]) -> dict[str, Any]:
        captured["path"] = path
        captured["data"] = data
        return {"cardId": "card-1", "dependencies": data["dependencies"]}

    client = FavroClient("e@example.com", "token")
    client._post = fake_post  # type: ignore[method-assign]

    client.add_card_dependencies(
        "card-1", [{"cardId": "dep-card", "isBefore": True}]
    )
    assert captured["path"] == "/cards/card-1/dependencies"
    assert captured["data"] == {
        "dependencies": [{"cardId": "dep-card", "isBefore": True}]
    }


def test_card_to_dict_surfaces_parent_card_id() -> None:
    card = Card.model_validate(
        {
            "cardId": "card-1",
            "organizationId": "org-1",
            "cardCommonId": "common-1",
            "name": "Child",
            "sequentialId": 1,
            "parentCardId": "parent-board-card-id",
        }
    )
    assert _card_to_dict(card)["parent_card_id"] == "parent-board-card-id"


def test_card_to_dict_parent_is_none_when_unset() -> None:
    card = Card.model_validate(
        {
            "cardId": "card-1",
            "organizationId": "org-1",
            "cardCommonId": "common-1",
            "name": "Orphan",
            "sequentialId": 1,
        }
    )
    assert _card_to_dict(card)["parent_card_id"] is None


def test_delete_card_dependency_hits_scoped_path() -> None:
    captured: dict[str, Any] = {}

    def fake_delete(path: str, params: Any = None) -> dict[str, Any]:
        captured["path"] = path
        return {}

    client = FavroClient("e@example.com", "token")
    client._delete = fake_delete  # type: ignore[method-assign]

    client.delete_card_dependency("card-1", "dep-card")
    assert captured["path"] == "/cards/card-1/dependencies/dep-card"

def test_update_card_sends_drag_mode() -> None:
    client, captured = _client_capturing_put()
    client.update_card(card_id="c0ffee01", widget_common_id="b0a2", drag_mode="commit")
    assert captured["data"]["dragMode"] == "commit"
    assert captured["data"]["widgetCommonId"] == "b0a2"


def test_update_card_omits_drag_mode_when_not_set() -> None:
    client, captured = _client_capturing_put()
    client.update_card(card_id="c0ffee01", widget_common_id="b0a2")
    assert "dragMode" not in captured["data"]


def _card(card_id: str, widget_common_id: str, sequential_id: int = 42) -> Card:
    return Card.model_validate(
        {
            "cardId": card_id,
            "organizationId": "org-1",
            "cardCommonId": "common-1",
            "name": "Card",
            "sequentialId": sequential_id,
            "widgetCommonId": widget_common_id,
        }
    )


def _widget(widget_common_id: str, name: str) -> Widget:
    return Widget.model_validate(
        {
            "widgetCommonId": widget_common_id,
            "organizationId": "org-1",
            "name": name,
            "type": "board",
        }
    )


class _FakeClient:
    """Just enough of FavroClient for the resolvers ``add_card_to_board`` uses."""

    def __init__(self, instances: list[Card], widgets: list[Widget]) -> None:
        self._instances = instances
        self._widgets = widgets
        self.update_calls: list[dict[str, Any]] = []
        self.get_cards_calls: list[dict[str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def get_card(self, card_id: str) -> Card:
        for c in self._instances:
            if c.card_id == card_id:
                return c
        raise ValueError(f"no such card: {card_id}")

    def get_widget(self, widget_id: str) -> Widget:
        for w in self._widgets:
            if w.widget_common_id == widget_id:
                return w
        raise ValueError(f"no such widget: {widget_id}")

    def get_cards(self, **kwargs: Any) -> list[Card]:
        self.get_cards_calls.append(kwargs)
        seq: int | None = kwargs.get("card_sequential_id")
        return [c for c in self._instances if seq is None or c.sequential_id == seq]

    def update_card(self, **kwargs: Any) -> Card:
        self.update_calls.append(kwargs)
        return _card("c0ffee99", str(kwargs["widget_common_id"]))


class _StubContext:
    """Stands in for FavroContext, handing the tool the fake client."""

    def __init__(self, client: _FakeClient) -> None:
        self._client = client
        self.current_board_id: str | None = None

    def require_org(self) -> str:
        return "org-1"

    def get_client(self) -> _FakeClient:
        return self._client


FakeFavro = Callable[[list[Card], list[Widget]], _FakeClient]


@pytest.fixture
def fake_favro(monkeypatch: pytest.MonkeyPatch) -> FakeFavro:
    """Point the card tools at a fake client, and hand it to the test."""

    def _build(instances: list[Card], widgets: list[Widget]) -> _FakeClient:
        client = _FakeClient(instances, widgets)
        stub = _StubContext(client)

        def _stub_context(_ctx: object) -> _StubContext:
            return stub

        monkeypatch.setattr(card_tools, "get_favro_context", _stub_context)
        return client

    return _build


def _no_ctx() -> Context:
    """The tools take a Context they never touch once the context is stubbed."""
    return cast(Context, None)


def test_add_card_to_board_copy_sends_commit(fake_favro: FakeFavro) -> None:
    client = fake_favro(
        [_card("c0ffee01", "b0a1")],
        [_widget("b0a1", "Planning"), _widget("b0a2", "Kanban")],
    )

    result = card_tools.add_card_to_board(
        card="c0ffee01", to_board="b0a2", ctx=_no_ctx(), mode="copy"
    )

    assert client.update_calls[0]["drag_mode"] == "commit"
    assert client.update_calls[0]["widget_common_id"] == "b0a2"
    assert result["kept_on_source_board"] is True
    assert result["already_present"] is False
    # The instance check has to see every instance, not one per cardCommonId.
    assert client.get_cards_calls[0]["unique"] is False


def test_add_card_to_board_move_sends_move(fake_favro: FakeFavro) -> None:
    client = fake_favro(
        [_card("c0ffee01", "b0a1")],
        [_widget("b0a1", "Planning"), _widget("b0a2", "Kanban")],
    )

    result = card_tools.add_card_to_board(
        card="c0ffee01", to_board="b0a2", ctx=_no_ctx(), mode="move"
    )

    assert client.update_calls[0]["drag_mode"] == "move"
    assert result["kept_on_source_board"] is False


def test_add_card_to_board_leaves_a_card_that_is_already_there(
    fake_favro: FakeFavro,
) -> None:
    client = fake_favro(
        [_card("c0ffee01", "b0a1"), _card("c0ffee02", "b0a2")],
        [_widget("b0a1", "Planning"), _widget("b0a2", "Kanban")],
    )

    result = card_tools.add_card_to_board(
        card="c0ffee01", to_board="b0a2", ctx=_no_ctx()
    )

    assert client.update_calls == []
    assert result["already_present"] is True
    assert result["card_id"] == "c0ffee02"
