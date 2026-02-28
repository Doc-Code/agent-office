"""System prompts and personality templates for agent roles."""

ROLE_PROMPTS: dict[str, str] = {
    "worker": (
        "You are a software engineer agent. You work autonomously on assigned tasks. "
        "When you receive a task, analyze it carefully, implement the solution, and "
        "report back with a summary of what you did. Focus on clean, working code. "
        "If you get stuck, describe the problem clearly so a supervisor can help."
    ),
    "reviewer": (
        "You are a code review agent. You review pull requests and code changes. "
        "Look for bugs, security issues, performance problems, and style violations. "
        "Provide constructive feedback with specific suggestions for improvement."
    ),
    "architect": (
        "You are a software architect agent. You design system architecture, "
        "plan implementations, and break down large tasks into smaller ones. "
        "Focus on clean separation of concerns and maintainable design."
    ),
}

REPO_CONTEXT: dict[str, str] = {
    "main-server": "Express/MongoDB/Keycloak backend. Routes in src/api/, services in src/services/.",
    "frontend_v2": "React 19 + HeroUI + Tailwind v4 frontend.",
    "telegram-channel": "Telegram bot channel integration.",
    "omni-channel": "Multi-channel message routing service.",
    "widget-go": "Go-based chat widget backend.",
    "oauth": "OAuth server (Python).",
    "oauth-ui": "OAuth UI frontend.",
    "nginx": "Nginx reverse proxy configs.",
    "cdn": "CDN/static asset service.",
}


def build_system_prompt(
    role: str = "worker",
    repo: str | None = None,
    extra: str | None = None,
) -> str:
    """Build a full system prompt for an agent."""
    parts = [ROLE_PROMPTS.get(role, ROLE_PROMPTS["worker"])]

    if repo and repo in REPO_CONTEXT:
        parts.append(f"\nProject context: {REPO_CONTEXT[repo]}")

    if extra:
        parts.append(f"\n{extra}")

    return "\n".join(parts)


def build_gupp_prompt(task_title: str, task_description: str | None = None) -> str:
    """Build a GUPP (Grand Unified Persistent Prompt) for task resumption."""
    parts = [
        "You are resuming work on a previously assigned task.",
        f"\nTask: {task_title}",
    ]
    if task_description:
        parts.append(f"\nDescription: {task_description[:2000]}")
    parts.append(
        "\nPlease continue where you left off. Check the current state of the code "
        "and complete the remaining work."
    )
    return "\n".join(parts)
