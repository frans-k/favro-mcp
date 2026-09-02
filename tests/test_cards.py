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
from favro_mcp.api.models import Card, Column, Widget
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


def _lane(card_id: str, widget_common_id: str, name: str) -> Card:
    """A swimlane — Favro models them as cards flagged ``isLane``."""
    lane = _card(card_id, widget_common_id, sequential_id=0)
    return lane.model_copy(update={"is_lane": True, "name": name})


def _column(column_id: str, widget_common_id: str, name: str) -> Column:
    return Column.model_validate(
        {
            "columnId": column_id,
            "organizationId": "org-1",
            "widgetCommonId": widget_common_id,
            "name": name,
            "position": 0.0,
        }
    )


class _FakeClient:
    """Just enough of FavroClient for the resolvers ``add_card_to_board`` uses."""

    def __init__(
        self,
        instances: list[Card],
        widgets: list[Widget],
        columns: list[Column] | None = None,
    ) -> None:
        self._instances = instances
        self._widgets = widgets
        self._columns = columns or []
        self.update_calls: list[dict[str, Any]] = []

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

    def get_column(self, column_id: str) -> Column:
        for col in self._columns:
            if col.column_id == column_id:
                return col
        raise ValueError(f"no such column: {column_id}")

    def get_columns(self, board_id: str) -> list[Column]:
        return [col for col in self._columns if col.widget_common_id == board_id]

    def get_lanes(self, board_id: str) -> list[Card]:
        return [
            c for c in self._instances if c.is_lane and c.widget_common_id == board_id
        ]

    def get_cards(self, **kwargs: Any) -> list[Card]:
        """Filters the way the real endpoint does, ``unique`` included.

        ``unique`` defaults to True on the client, and that default is why a
        sequential id resolves a multi-board card to one arbitrary instance —
        the reason a move insists on knowing its source board.
        """
        seq: int | None = kwargs.get("card_sequential_id")
        widget: str | None = kwargs.get("widget_common_id")
        unique: bool = kwargs.get("unique", True)

        found = [c for c in self._instances if seq is None or c.sequential_id == seq]
        if widget is not None:
            found = [c for c in found if c.widget_common_id == widget]
        if unique:
            seen: set[str] = set()
            deduped: list[Card] = []
            for c in found:
                if c.card_common_id not in seen:
                    seen.add(c.card_common_id)
                    deduped.append(c)
            found = deduped
        return found

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


FakeFavro = Callable[..., _FakeClient]
"""``_build(instances, widgets, columns=None, selected_board=None)``."""


@pytest.fixture
def fake_favro(monkeypatch: pytest.MonkeyPatch) -> FakeFavro:
    """Point the card tools at a fake client, and hand it to the test."""

    def _build(
        instances: list[Card],
        widgets: list[Widget],
        columns: list[Column] | None = None,
        selected_board: str | None = None,
    ) -> _FakeClient:
        client = _FakeClient(instances, widgets, columns)
        stub = _StubContext(client)
        stub.current_board_id = selected_board

        def _stub_context(_ctx: object) -> _StubContext:
            return stub

        monkeypatch.setattr(card_tools, "get_favro_context", _stub_context)
        return client

    return _build


def _no_ctx() -> Context:
    """The tools take a Context they never touch once the context is stubbed."""
    return cast(Context, None)


def _two_board_card() -> list[Card]:
    """One card with an instance on each of two boards."""
    return [_card("c0ffee01", "b0a1"), _card("c0ffee02", "b0a2")]


def _two_boards() -> list[Widget]:
    return [_widget("b0a1", "Planning"), _widget("b0a2", "Kanban")]


def test_add_card_to_board_copy_sends_commit(fake_favro: FakeFavro) -> None:
    client = fake_favro([_card("c0ffee01", "b0a1")], _two_boards())

    result = card_tools.add_card_to_board(
        card="c0ffee01", to_board="b0a2", ctx=_no_ctx(), mode="copy"
    )

    assert client.update_calls[0]["drag_mode"] == "commit"
    assert client.update_calls[0]["widget_common_id"] == "b0a2"
    assert result["board_id"] == "b0a2"
    assert result["source_board_id"] == "b0a1"


def test_add_card_to_board_move_sends_move(fake_favro: FakeFavro) -> None:
    client = fake_favro([_card("c0ffee01", "b0a1")], _two_boards())

    result = card_tools.add_card_to_board(
        card="c0ffee01", to_board="b0a2", ctx=_no_ctx(), mode="move"
    )

    assert client.update_calls[0]["drag_mode"] == "move"
    # The board that loses the card, which the caller may not have named.
    assert result["source_board_id"] == "b0a1"


def test_add_card_to_board_move_needs_a_source_board_for_a_sequential_id(
    fake_favro: FakeFavro,
) -> None:
    client = fake_favro(_two_board_card(), _two_boards())

    with pytest.raises(ValueError, match="does not say which board to move"):
        card_tools.add_card_to_board(
            card="#42", to_board="b0a2", ctx=_no_ctx(), mode="move"
        )

    assert client.update_calls == []


def test_add_card_to_board_move_takes_a_sequential_id_with_a_source_board(
    fake_favro: FakeFavro,
) -> None:
    client = fake_favro(_two_board_card(), _two_boards())

    card_tools.add_card_to_board(
        card="#42", to_board="b0a2", ctx=_no_ctx(), mode="move", board="b0a1"
    )

    assert client.update_calls[0]["drag_mode"] == "move"
    assert client.update_calls[0]["card_id"] == "c0ffee01"


def test_add_card_to_board_move_by_card_id_needs_no_source_board(
    fake_favro: FakeFavro,
) -> None:
    client = fake_favro(_two_board_card(), _two_boards())

    card_tools.add_card_to_board(
        card="c0ffee01", to_board="b0a2", ctx=_no_ctx(), mode="move"
    )

    assert client.update_calls[0]["drag_mode"] == "move"
    assert client.update_calls[0]["card_id"] == "c0ffee01"


def test_add_card_to_board_move_refuses_a_source_board_the_card_is_not_on(
    fake_favro: FakeFavro,
) -> None:
    """CardResolver's direct-id path ignores board_id, so the two can disagree."""
    client = fake_favro(_two_board_card(), _two_boards())

    with pytest.raises(ValueError, match="board you did not ask for"):
        card_tools.add_card_to_board(
            card="c0ffee02",  # the instance on b0a2
            to_board="b0a1",
            ctx=_no_ctx(),
            mode="move",
            board="b0a1",  # ...but this names b0a1 as the source
        )

    assert client.update_calls == []


def test_add_card_to_board_move_refuses_a_mismatched_board_from_set_board(
    fake_favro: FakeFavro,
) -> None:
    """A board selected with set_board has to agree too, not just an explicit one."""
    client = fake_favro(
        _two_board_card(),
        [*_two_boards(), _widget("b0a3", "Ops")],
        selected_board="b0a1",
    )

    with pytest.raises(ValueError, match="board you did not ask for"):
        card_tools.add_card_to_board(
            card="c0ffee02",  # the instance on b0a2, not the selected b0a1
            to_board="b0a3",
            ctx=_no_ctx(),
            mode="move",
        )

    assert client.update_calls == []


def test_add_card_to_board_copy_tolerates_a_mismatched_source_board(
    fake_favro: FakeFavro,
) -> None:
    """A copy lands on the destination whichever instance is sent, so no refusal."""
    client = fake_favro(_two_board_card(), [*_two_boards(), _widget("b0a3", "Ops")])

    card_tools.add_card_to_board(
        card="c0ffee02", to_board="b0a3", ctx=_no_ctx(), mode="copy", board="b0a1"
    )

    assert client.update_calls[0]["drag_mode"] == "commit"


def test_add_card_to_board_resolves_placement_on_the_destination_board(
    fake_favro: FakeFavro,
) -> None:
    client = fake_favro(
        [_card("c0ffee01", "b0a1")],
        _two_boards(),
        [_column("col-doing", "b0a2", "In progress")],
    )

    result = card_tools.add_card_to_board(
        card="c0ffee01", to_board="b0a2", ctx=_no_ctx(), column="In progress"
    )

    assert client.update_calls[0]["column_id"] == "col-doing"
    assert result["column_name"] == "In progress"
    assert "In progress" in str(result["message"])


def test_add_card_to_board_copy_still_commits_when_already_on_the_destination(
    fake_favro: FakeFavro,
) -> None:
    """The removed short-circuit's case: the copy is sent, not skipped.

    Favro models one ``cardId`` per widget per ``cardCommonId``, so ``commit``
    against a board that already holds an instance should be a no-op rather
    than a duplicate. Pinned here so a re-introduced short-circuit shows up as
    a behaviour change.
    """
    client = fake_favro(_two_board_card(), _two_boards())

    result = card_tools.add_card_to_board(
        card="c0ffee01", to_board="b0a2", ctx=_no_ctx(), mode="copy"
    )

    assert client.update_calls[0]["drag_mode"] == "commit"
    # Sent against the source instance; Favro decides what the destination
    # instance ends up being.
    assert client.update_calls[0]["card_id"] == "c0ffee01"
    assert client.update_calls[0]["widget_common_id"] == "b0a2"
    assert result["board_id"] == "b0a2"
    assert result["source_board_id"] == "b0a1"


def test_add_card_to_board_move_to_the_board_the_card_is_already_on(
    fake_favro: FakeFavro,
) -> None:
    """Source equals destination: the request goes out rather than being skipped."""
    client = fake_favro(_two_board_card(), _two_boards())

    result = card_tools.add_card_to_board(
        card="c0ffee02", to_board="b0a2", ctx=_no_ctx(), mode="move"
    )

    assert client.update_calls[0]["drag_mode"] == "move"
    assert client.update_calls[0]["card_id"] == "c0ffee02"
    assert client.update_calls[0]["widget_common_id"] == "b0a2"
    # Nowhere to move it off, so the source board is the destination.
    assert result["source_board_id"] == "b0a2"


def test_add_card_to_board_applies_a_lane_and_names_it(fake_favro: FakeFavro) -> None:
    """The message used to drop the lane it had just applied."""
    client = fake_favro(
        [_card("c0ffee01", "b0a1"), _lane("lane-platform", "b0a2", "Platform")],
        _two_boards(),
        [_column("col-doing", "b0a2", "In progress")],
    )

    result = card_tools.add_card_to_board(
        card="c0ffee01",
        to_board="b0a2",
        ctx=_no_ctx(),
        column="In progress",
        lane="Platform",
    )

    # A lane's id is its cardId, not a columnId.
    assert client.update_calls[0]["lane_id"] == "lane-platform"
    assert result["lane_name"] == "Platform"
    assert "column 'In progress' and lane 'Platform'" in str(result["message"])
