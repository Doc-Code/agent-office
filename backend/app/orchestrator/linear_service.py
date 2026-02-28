"""Linear API integration — fetch issues, update status, assign agents."""

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearService:
    """Async client for Linear GraphQL API."""

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.linear_api_key
        self.team_id = settings.linear_team_id
        self.project_id = settings.linear_project_id

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _request(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL request against Linear API."""
        if not self.api_key:
            raise RuntimeError("Linear API key not configured")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                LINEAR_API_URL,
                json={"query": query, "variables": variables or {}},
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                logger.error("Linear GraphQL errors: %s", data["errors"])
                raise RuntimeError(f"Linear API error: {data['errors'][0].get('message', 'Unknown')}")
            return data.get("data", {})

    async def get_team_states(self) -> list[dict[str, str]]:
        """Get all workflow states for the configured team."""
        data = await self._request(
            """query TeamStates($teamId: String!) {
                team(id: $teamId) {
                    states { nodes { id name type } }
                }
            }""",
            {"teamId": self.team_id},
        )
        return data.get("team", {}).get("states", {}).get("nodes", [])

    async def get_issues(
        self,
        state_names: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch issues from the configured team, optionally filtered by state."""
        filter_parts = [f'team: {{ id: {{ eq: "{self.team_id}" }} }}']
        if self.project_id:
            filter_parts.append(f'project: {{ id: {{ eq: "{self.project_id}" }} }}')
        if state_names:
            names_str = ", ".join(f'"{s}"' for s in state_names)
            filter_parts.append(f"state: {{ name: {{ in: [{names_str}] }} }}")

        filter_str = ", ".join(filter_parts)

        data = await self._request(
            f"""query Issues($first: Int) {{
                issues(filter: {{ {filter_str} }}, first: $first, orderBy: updatedAt) {{
                    nodes {{
                        id
                        identifier
                        title
                        description
                        priority
                        state {{ id name }}
                        assignee {{ id name }}
                        labels {{ nodes {{ id name }} }}
                        url
                        createdAt
                        updatedAt
                    }}
                }}
            }}""",
            {"first": limit},
        )
        return data.get("issues", {}).get("nodes", [])

    async def get_issue(self, issue_id: str) -> dict[str, Any] | None:
        """Fetch a single issue by ID."""
        data = await self._request(
            """query Issue($id: String!) {
                issue(id: $id) {
                    id
                    identifier
                    title
                    description
                    priority
                    state { id name }
                    assignee { id name }
                    labels { nodes { id name } }
                    url
                    createdAt
                    updatedAt
                }
            }""",
            {"id": issue_id},
        )
        return data.get("issue")

    async def update_issue_state(self, issue_id: str, state_name: str) -> bool:
        """Update issue workflow state by name."""
        states = await self.get_team_states()
        state = next((s for s in states if s["name"].lower() == state_name.lower()), None)
        if not state:
            logger.warning("State '%s' not found in team states", state_name)
            return False

        data = await self._request(
            """mutation UpdateIssueState($id: String!, $input: IssueUpdateInput!) {
                issueUpdate(id: $id, input: $input) { success }
            }""",
            {"id": issue_id, "input": {"stateId": state["id"]}},
        )
        return data.get("issueUpdate", {}).get("success", False)

    async def add_comment(self, issue_id: str, body: str) -> dict[str, Any] | None:
        """Add a comment to an issue."""
        data = await self._request(
            """mutation CreateComment($input: CommentCreateInput!) {
                commentCreate(input: $input) {
                    success
                    comment { id body createdAt }
                }
            }""",
            {"input": {"issueId": issue_id, "body": body}},
        )
        result = data.get("commentCreate", {})
        return result.get("comment") if result.get("success") else None

    async def create_issue(
        self,
        title: str,
        description: str = "",
        priority: int = 3,
        label_ids: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Create a new issue in the configured team/project."""
        issue_input: dict[str, Any] = {
            "title": title,
            "description": description,
            "teamId": self.team_id,
            "priority": priority,
        }
        if self.project_id:
            issue_input["projectId"] = self.project_id
        if label_ids:
            issue_input["labelIds"] = label_ids

        data = await self._request(
            """mutation CreateIssue($input: IssueCreateInput!) {
                issueCreate(input: $input) {
                    success
                    issue { id identifier title url state { name } }
                }
            }""",
            {"input": issue_input},
        )
        result = data.get("issueCreate", {})
        return result.get("issue") if result.get("success") else None


_linear_service: LinearService | None = None


def get_linear_service() -> LinearService:
    global _linear_service  # noqa: PLW0603
    if _linear_service is None:
        _linear_service = LinearService()
    return _linear_service
