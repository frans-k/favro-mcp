"""Lane (swimlane) resolver (requires board context for name resolution)."""

from favro_mcp.api.client import FavroNotFoundError
from favro_mcp.api.models import Card

from .base import BaseResolver


class LaneResolver(BaseResolver[Card]):
    """Resolver for board swimlanes.

    Favro models swimlanes as cards flagged with ``isLane``; a card's
    ``laneId`` references the lane card's ``cardId``. Lane names are only
    unique within a board, so ``board_id`` context is required for name
    resolution.
    """

    entity_type = "lane"

    def _fetch_all(
        self, board_id: str | None = None, **context: str | None
    ) -> list[Card]:
        if board_id is None:
            raise ValueError("board_id is required to resolve lanes by name")
        return self.client.get_lanes(board_id)

    def _fetch_by_id(self, entity_id: str) -> Card | None:
        try:
            card = self.client.get_card(entity_id)
        except FavroNotFoundError:
            return None
        return card if card.is_lane else None

    def _get_id(self, entity: Card) -> str:
        return entity.card_id

    def _get_name(self, entity: Card) -> str:
        return entity.name
