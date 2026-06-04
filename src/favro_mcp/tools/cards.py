"""Card tools for Favro MCP."""

from typing import Any

from fastmcp import Context

from favro_mcp.api.models import Card
from favro_mcp.context import get_favro_context
from favro_mcp.resolvers import (
    BoardResolver,
    CardResolver,
    ColumnResolver,
    LaneResolver,
    TagResolver,
    UserResolver,
)
from favro_mcp.server import mcp


def _strip_tasklist_from_description(
    description: str | None,
    tasklists: list[dict[str, Any]],
) -> str | None:
    """Strip auto-appended tasklist checkboxes from description.

    Favro's API appends tasklist items as checkbox characters to the
    detailedDescription field. This function removes those trailing
    lines to prevent duplication when updating.

    Args:
        description: The card's detailed description
        tasklists: List of tasklist dicts with 'name' and 'tasks' keys

    Returns:
        The description with trailing tasklist checkboxes removed
    """
    if not description or not tasklists:
        return description

    lines = description.rstrip().split("\n")

    # Build set of expected checkbox patterns
    checkbox_patterns: set[str] = set()
    tasklist_names: set[str] = set()
    for tasklist in tasklists:
        tasklist_names.add(tasklist.get("name", ""))
        for task in tasklist.get("tasks", []):
            task_name = task.get("name", "")
            checkbox_patterns.add(f"☐ {task_name}")
            checkbox_patterns.add(f"☑ {task_name}")

    # Strip trailing lines that match tasklist/task patterns
    while lines:
        line = lines[-1].strip()
        if not line:
            lines.pop()
        elif line in checkbox_patterns or line in tasklist_names:
            lines.pop()
        else:
            break

    return "\n".join(lines) if lines else ""


def _card_to_dict(card: Card) -> dict[str, Any]:
    """Convert a Card to a dictionary for JSON serialization."""
    return {
        "card_id": card.card_id,
        "card_common_id": card.card_common_id,
        "sequential_id": card.sequential_id,
        "name": card.name,
        "detailed_description": card.detailed_description,
        "widget_common_id": card.widget_common_id,
        "column_id": card.column_id,
        "lane_id": card.lane_id,
        "tags": card.tags,
        "assignments": [
            {"user_id": a.user_id, "completed": a.completed} for a in card.assignments
        ],
        "start_date": card.start_date.isoformat() if card.start_date else None,
        "due_date": card.due_date.isoformat() if card.due_date else None,
        "archived": card.archived,
        "tasks_done": card.tasks_done,
        "tasks_total": card.tasks_total,
        "time_on_board": card.time_on_board,
        "custom_fields": [
            {
                "custom_field_id": cf.custom_field_id,
                "value": cf.value,
                "total": cf.total,
                "link": cf.link,
                "members": cf.members,
                "color": cf.color,
            }
            for cf in card.custom_fields
        ],
    }


@mcp.tool
def list_cards(
    board: str,
    ctx: Context,
    column: str | None = None,
    page: int = 0,
) -> dict[str, Any]:
    """List cards on a specific board with pagination.

    Args:
        board: The board's widget_common_id, name, or ID
        column: Optional column ID or name to filter by
        page: Page number (0-indexed, default 0). Each page contains up to 100 cards.

    Returns:
        A list of cards with pagination metadata.
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        board_id = BoardResolver(client).resolve(board).widget_common_id

        # Resolve column if provided
        column_id = None
        if column:
            column_id = ColumnResolver(client).resolve(column, board_id=board_id).column_id

        cards, total_pages = client.get_cards_page(
            widget_common_id=board_id,
            column_id=column_id,
            page=page,
        )

        result = [
            {
                "card_id": card.card_id,
                "sequential_id": card.sequential_id,
                "name": card.name,
                "column_id": card.column_id,
                "tags": card.tags,
                "archived": card.archived,
            }
            for card in cards
        ]
        return {
            "cards": result,
            "page": page,
            "total_pages": total_pages,
            "cards_on_page": len(result),
        }


@mcp.tool
def list_lanes(board: str, ctx: Context) -> dict[str, Any]:
    """List the swimlanes on a board.

    On boards that use swimlanes, the lane is the work type
    (e.g. Platform / Support / Ops). Use a returned ``lane_id`` or name with
    ``create_card(lane=...)`` or ``move_card(lane=...)``.

    Args:
        board: The board's widget_common_id, name, or ID

    Returns:
        A list of lanes with their IDs and names.
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        board_id = BoardResolver(client).resolve(board).widget_common_id
        lanes = client.get_lanes(board_id)
        return {
            "lanes": [{"lane_id": lane.card_id, "name": lane.name} for lane in lanes]
        }


@mcp.tool
def list_custom_fields(
    ctx: Context,
    name: str | None = None,
    field_type: str | None = None,
) -> dict[str, Any]:
    """List custom fields in the organization.

    Args:
        name: Filter by name (case-insensitive substring match)
        field_type: Filter by type (e.g., "Link", "Text", "Rating", "Single select")

    Returns:
        Custom field definitions with IDs, names, and types.
        Use the customFieldId when updating card custom fields.
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        fields = client.get_custom_fields()

        # Apply filters
        if name:
            name_lower = name.lower()
            fields = [f for f in fields if name_lower in f.get("name", "").lower()]
        if field_type:
            type_lower = field_type.lower()
            fields = [f for f in fields if f.get("type", "").lower() == type_lower]

        # Return minimal info
        result = [
            {"customFieldId": f["customFieldId"], "name": f["name"], "type": f["type"]}
            for f in fields
        ]
        return {"custom_fields": result, "count": len(result)}


@mcp.tool
def get_card_details(card: str, ctx: Context, board: str | None = None) -> dict[str, Any]:
    """Get detailed information about a specific card.

    Args:
        card: Card ID, sequential ID (#123), or name
        board: Board ID or name (needed for name lookups)

    Returns:
        Full card details including description, assignments, dates, custom fields,
        task lists with their tasks, and comments.
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        board_id = board or favro_ctx.current_board_id
        if board:
            board_id = BoardResolver(client).resolve(board).widget_common_id
        c = CardResolver(client).resolve(card, board_id=board_id)

        # Fetch task lists and their tasks
        tasklists_data: list[dict[str, Any]] = []
        tasklists = client.get_tasklists(c.card_common_id)
        for tasklist in tasklists:
            tasks = client.get_tasks(c.card_common_id, tasklist.tasklist_id)
            tasklists_data.append(
                {
                    "tasklist_id": tasklist.tasklist_id,
                    "name": tasklist.name,
                    "position": tasklist.position,
                    "tasks": [
                        {
                            "task_id": task.task_id,
                            "name": task.name,
                            "completed": task.completed,
                            "position": task.position,
                        }
                        for task in tasks
                    ],
                }
            )

        # Fetch comments
        comments = client.get_comments(c.card_common_id)
        comments_data = [
            {
                "comment_id": comment.comment_id,
                "user_id": comment.user_id,
                "comment": comment.comment,
                "created": comment.created.isoformat(),
                "last_updated": comment.last_updated.isoformat() if comment.last_updated else None,
            }
            for comment in comments
        ]

        result = _card_to_dict(c)
        result["tasklists"] = tasklists_data
        result["comments"] = comments_data
        # Clean description to remove auto-appended tasklist checkboxes
        result["detailed_description"] = _strip_tasklist_from_description(
            result["detailed_description"], tasklists_data
        )
        return result


@mcp.tool
def add_comment(
    card: str,
    comment: str,
    ctx: Context,
    board: str | None = None,
) -> dict[str, Any]:
    """Add a comment to a card.

    Args:
        card: Card ID, sequential ID (#123), or name
        comment: Comment text to post
        board: Board ID or name (needed for name lookup; optional for sequential ID)

    Returns:
        The created comment metadata.
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        board_id = board or favro_ctx.current_board_id
        if board:
            board_id = BoardResolver(client).resolve(board).widget_common_id

        c = CardResolver(client).resolve(card, board_id=board_id)
        created = client.create_comment(c.card_common_id, comment)

        return {
            "message": "Comment added",
            "comment_id": created.comment_id,
            "card_common_id": created.card_common_id,
            "user_id": created.user_id,
            "created": created.created.isoformat(),
        }


@mcp.tool
def create_card(
    name: str,
    ctx: Context,
    board: str | None = None,
    column: str | None = None,
    lane: str | None = None,
    parent: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    assignees: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new card.

    Args:
        name: Card name/title
        board: Board ID or name (uses current board if not specified)
        column: Column ID or name to place the card in
        lane: Swimlane ID or name to place the card in. On boards that use
            swimlanes, the lane is the work type (e.g. Platform / Support / Ops).
        parent: Parent card ID, sequential ID (e.g. #263556), or name to nest this card under
        description: Detailed description (supports markdown)
        tags: List of tag IDs or names to add
        assignees: List of user IDs, names, or emails to assign

    Returns:
        The created card details
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        board_id = board or favro_ctx.current_board_id
        if not board_id:
            raise ValueError("No board specified and no current board selected.")
        if board:
            board_id = BoardResolver(client).resolve(board).widget_common_id

        # Resolve column if provided
        column_id = None
        if column:
            column_id = ColumnResolver(client).resolve(column, board_id=board_id).column_id

        # Resolve lane (swimlane / work type) if provided. The laneId expected
        # by the API is the lane card's card_id.
        lane_id = None
        if lane:
            lane_id = LaneResolver(client).resolve(lane, board_id=board_id).card_id

        # Resolve parent card if provided.
        # parentCardId requires the board-specific card_id, which differs
        # from the card_id returned by get_card. We resolve to
        # card_common_id first, then find the board-specific card_id
        # by listing cards on the target board.
        parent_card_id = None
        if parent:
            parent_common_id = CardResolver(client).resolve(parent, board_id=board_id).card_common_id
            board_cards = client.get_cards(widget_common_id=board_id)
            board_card = next(
                (c for c in board_cards if c.card_common_id == parent_common_id),
                None,
            )
            if board_card is None:
                raise ValueError(
                    f"Parent card '{parent}' not found on the target board."
                )
            parent_card_id = board_card.card_id

        # Resolve tags if provided
        tag_ids = None
        if tags:
            tag_resolver = TagResolver(client)
            tag_ids = [tag_resolver.resolve(t).tag_id for t in tags]

        # Resolve assignees if provided
        user_ids = None
        if assignees:
            user_resolver = UserResolver(client)
            user_ids = [user_resolver.resolve(u).user_id for u in assignees]

        card = client.create_card(
            name=name,
            widget_common_id=board_id,
            column_id=column_id,
            lane_id=lane_id,
            parent_card_id=parent_card_id,
            detailed_description=description,
            tags=tag_ids,
            assignments=user_ids,
        )

        return {
            "message": f"Created card #{card.sequential_id}: {card.name}",
            "card_id": card.card_id,
            "card_common_id": card.card_common_id,
            "sequential_id": card.sequential_id,
            "name": card.name,
        }


@mcp.tool
def set_card(card: str, ctx: Context, board: str | None = None) -> dict[str, Any]:
    """Select a card as the active card for subsequent operations.

    This sets the default card for update operations such as update_card,
    set_custom_fields, update_tasks, create_tasklist, create_task, and delete_tasklist.

    Args:
        card: Card ID, sequential ID (#123), or name
        board: Board ID or name (needed for name lookups; uses current board if omitted)

    Returns:
        The selected card details
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        board_id = board or favro_ctx.current_board_id
        if board:
            board_id = BoardResolver(client).resolve(board).widget_common_id

        c = CardResolver(client).resolve(card, board_id=board_id)
        favro_ctx.current_card_id = c.card_common_id
        favro_ctx.current_card_widget_card_id = c.card_id

        return {
            "message": f"Selected card #{c.sequential_id}: {c.name}",
            "card_common_id": c.card_common_id,
            "sequential_id": c.sequential_id,
            "name": c.name,
        }


@mcp.tool
def get_current_card(ctx: Context) -> dict[str, Any]:
    """Get details of the currently selected card.

    Returns:
        Full card details, or a message if no card is selected.
    """
    favro_ctx = get_favro_context(ctx)
    if not favro_ctx.current_card_id:
        return {"message": "No card selected. Use set_card tool first."}

    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        c = client.get_card(favro_ctx.require_card_widget_id())

        tasklists_data: list[dict[str, Any]] = []
        tasklists = client.get_tasklists(c.card_common_id)
        for tasklist in tasklists:
            tasks = client.get_tasks(c.card_common_id, tasklist.tasklist_id)
            tasklists_data.append(
                {
                    "tasklist_id": tasklist.tasklist_id,
                    "name": tasklist.name,
                    "position": tasklist.position,
                    "tasks": [
                        {
                            "task_id": task.task_id,
                            "name": task.name,
                            "completed": task.completed,
                            "position": task.position,
                        }
                        for task in tasks
                    ],
                }
            )

        result = _card_to_dict(c)
        result["tasklists"] = tasklists_data
        result["detailed_description"] = _strip_tasklist_from_description(
            result["detailed_description"], tasklists_data
        )
        return result


@mcp.tool
def update_card(
    ctx: Context,
    name: str | None = None,
    description: str | None = None,
    archived: bool | None = None,
) -> dict[str, Any]:
    """Update basic properties of the selected card.

    Requires a card to be selected with set_card first.

    Args:
        name: New card name
        description: New detailed description (supports markdown)
        archived: Archive (True) or unarchive (False) the card

    Returns:
        The updated card details
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    card_id = favro_ctx.require_card_widget_id()
    with favro_ctx.get_client() as client:
        updated = client.update_card(
            card_id=card_id,
            name=name,
            detailed_description=description,
            archived=archived,
        )
        return {
            "message": f"Updated card: {updated.name}",
            "card_id": updated.card_id,
            "sequential_id": updated.sequential_id,
            "name": updated.name,
        }


@mcp.tool
def set_custom_fields(
    custom_fields: list[dict[str, Any]],
    ctx: Context,
) -> dict[str, Any]:
    """Update custom field values on the selected card.

    Requires a card to be selected with set_card first.

    Args:
        custom_fields: List of custom field updates. Each dict should contain
            'customFieldId' and the appropriate value field for the field type:
            - Text: {'customFieldId': '...', 'value': 'text'}
            - Number/Rating: {'customFieldId': '...', 'total': 5}
            - Link: {'customFieldId': '...', 'link': {'url': '...', 'text': '...'}}
            - Checkbox: {'customFieldId': '...', 'value': True}
            - Date: {'customFieldId': '...', 'value': '2024-01-15'}
            - Status: {'customFieldId': '...', 'value': ['itemId1', 'itemId2']}

    Returns:
        The updated card details
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    card_id = favro_ctx.require_card_widget_id()
    with favro_ctx.get_client() as client:
        updated = client.update_card(card_id=card_id, custom_fields=custom_fields)
        return {
            "message": f"Updated custom fields on card: {updated.name}",
            "card_id": updated.card_id,
            "sequential_id": updated.sequential_id,
            "name": updated.name,
        }


@mcp.tool
def update_tasks(
    tasks: list[dict[str, Any]],
    ctx: Context,
) -> dict[str, Any]:
    """Update existing tasks on the selected card.

    Requires a card to be selected with set_card first.

    Args:
        tasks: List of task updates. Each dict should contain 'task_id' and optionally
            'completed' (bool) or 'name' (str) to update

    Returns:
        Confirmation of the updates
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    favro_ctx.require_card()
    with favro_ctx.get_client() as client:
        for task_update in tasks:
            task_id = task_update.get("task_id")
            if not task_id:
                continue
            client.update_task(
                task_id=task_id,
                name=task_update.get("name"),
                completed=task_update.get("completed"),
            )
        return {"message": f"Updated {len(tasks)} task(s)"}


@mcp.tool
def create_tasklist(
    name: str,
    ctx: Context,
    tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a new task list on the selected card.

    Requires a card to be selected with set_card first.

    Args:
        name: Name of the new task list
        tasks: Optional list of tasks to add inline:
            [{'name': 'Task 1'}, {'name': 'Task 2', 'completed': true}]

    Returns:
        The created task list details
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    card_common_id = favro_ctx.require_card()
    with favro_ctx.get_client() as client:
        new_tasklist = client.create_tasklist(card_common_id, name, tasks=tasks)
        task_count = len(new_tasklist.tasks) if new_tasklist.tasks else 0
        msg = f"Created task list: {new_tasklist.name}"
        if task_count:
            msg += f" ({task_count} tasks)"
        return {
            "message": msg,
            "tasklist_id": new_tasklist.tasklist_id,
            "name": new_tasklist.name,
            "task_count": task_count,
        }


@mcp.tool
def create_task(
    tasklist_id: str,
    name: str,
    ctx: Context,
) -> dict[str, Any]:
    """Create a new task in a task list on the selected card.

    Requires a card to be selected with set_card first.

    Args:
        tasklist_id: The task list ID to add the task to
        name: Name of the new task

    Returns:
        The created task details
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    favro_ctx.require_card()
    with favro_ctx.get_client() as client:
        new_task = client.create_task(tasklist_id, name)
        return {
            "message": f"Created task: {new_task.name}",
            "task_id": new_task.task_id,
            "name": new_task.name,
        }


@mcp.tool
def delete_tasklist(
    tasklist_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Delete a task list from the selected card.

    Requires a card to be selected with set_card first.

    Args:
        tasklist_id: The task list ID to delete

    Returns:
        Confirmation of deletion
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    favro_ctx.require_card()
    with favro_ctx.get_client() as client:
        client.delete_tasklist(tasklist_id)
        return {"message": f"Deleted task list: {tasklist_id}"}


@mcp.tool
def move_card(
    card: str,
    ctx: Context,
    column: str | None = None,
    lane: str | None = None,
    board: str | None = None,
) -> dict[str, Any]:
    """Move a card to a different column and/or swimlane.

    Provide at least one of ``column`` or ``lane``. On boards that use
    swimlanes, the lane is the work type (e.g. Platform / Support / Ops),
    while the column is the flow stage.

    Args:
        card: Card ID, sequential ID (#123), or name
        column: Target column ID or name (flow stage)
        lane: Target swimlane ID or name (work type)
        board: Board ID or name (needed for name lookups)

    Returns:
        The updated card details
    """
    if not column and not lane:
        raise ValueError("Provide at least one of 'column' or 'lane'.")

    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        board_id = board or favro_ctx.current_board_id
        if board:
            board_id = BoardResolver(client).resolve(board).widget_common_id

        c = CardResolver(client).resolve(card, board_id=board_id)

        # Use the card's board if not specified
        target_board = board_id or c.widget_common_id
        if not target_board:
            raise ValueError("Board ID required to resolve column/lane")

        col = None
        if column:
            col = ColumnResolver(client).resolve(column, board_id=target_board)

        lane_obj = None
        if lane:
            lane_obj = LaneResolver(client).resolve(lane, board_id=target_board)

        updated = client.update_card(
            card_id=c.card_id,
            column_id=col.column_id if col else None,
            lane_id=lane_obj.card_id if lane_obj else None,
            widget_common_id=target_board,
        )

        destination = " and ".join(
            part
            for part in (
                f"column '{col.name}'" if col else "",
                f"lane '{lane_obj.name}'" if lane_obj else "",
            )
            if part
        )
        return {
            "message": f"Moved card '{updated.name}' to {destination}",
            "card_id": updated.card_id,
            "column_id": col.column_id if col else None,
            "column_name": col.name if col else None,
            "lane_id": lane_obj.card_id if lane_obj else None,
            "lane_name": lane_obj.name if lane_obj else None,
        }


@mcp.tool
def assign_card(
    card: str,
    user: str,
    ctx: Context,
    board: str | None = None,
    remove: bool = False,
) -> dict[str, Any]:
    """Assign or unassign a user from a card.

    Args:
        card: Card ID, sequential ID (#123), or name
        user: User ID, name, or email
        board: Board ID or name (needed for name lookups)
        remove: If True, remove the assignment instead of adding

    Returns:
        The updated card details
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        board_id = board or favro_ctx.current_board_id
        if board:
            board_id = BoardResolver(client).resolve(board).widget_common_id

        c = CardResolver(client).resolve(card, board_id=board_id)
        u = UserResolver(client).resolve(user)

        if remove:
            updated = client.update_card(card_id=c.card_id, remove_assignments=[u.user_id])
            action = "Unassigned"
            prep = "from"
        else:
            updated = client.update_card(card_id=c.card_id, add_assignments=[u.user_id])
            action = "Assigned"
            prep = "to"

        return {
            "message": f"{action} {u.name} {prep} card '{updated.name}'",
            "card_id": updated.card_id,
            "user_id": u.user_id,
            "user_name": u.name,
        }


@mcp.tool
def tag_card(
    card: str,
    tag: str,
    ctx: Context,
    board: str | None = None,
    remove: bool = False,
) -> dict[str, Any]:
    """Add or remove a tag from a card.

    Args:
        card: Card ID, sequential ID (#123), or name
        tag: Tag ID or name
        board: Board ID or name (needed for name lookups)
        remove: If True, remove the tag instead of adding

    Returns:
        The updated card details
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        board_id = board or favro_ctx.current_board_id
        if board:
            board_id = BoardResolver(client).resolve(board).widget_common_id

        c = CardResolver(client).resolve(card, board_id=board_id)
        t = TagResolver(client).resolve(tag)

        if remove:
            updated = client.update_card(card_id=c.card_id, remove_tags=[t.tag_id])
            action = "Removed"
            prep = "from"
        else:
            updated = client.update_card(card_id=c.card_id, add_tags=[t.tag_id])
            action = "Added"
            prep = "to"

        return {
            "message": f"{action} tag '{t.name}' {prep} card '{updated.name}'",
            "card_id": updated.card_id,
            "tag_id": t.tag_id,
            "tag_name": t.name,
        }


@mcp.tool
def delete_card(
    card: str,
    ctx: Context,
    board: str | None = None,
    everywhere: bool = False,
) -> dict[str, Any]:
    """Delete a card.

    Args:
        card: Card ID, sequential ID (#123), or name
        board: Board ID or name (needed for name lookups)
        everywhere: If True, delete from all boards (not just current)

    Returns:
        Confirmation of deletion
    """
    favro_ctx = get_favro_context(ctx)
    favro_ctx.require_org()
    with favro_ctx.get_client() as client:
        board_id = board or favro_ctx.current_board_id
        if board:
            board_id = BoardResolver(client).resolve(board).widget_common_id

        c = CardResolver(client).resolve(card, board_id=board_id)
        card_name = c.name
        card_id = c.card_id

        client.delete_card(card_id, everywhere=everywhere)

        return {
            "message": f"Deleted card: {card_name}",
            "card_id": card_id,
        }
