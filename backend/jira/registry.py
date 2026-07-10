"""Named Jira instance registry, mirroring the LLM factory boundary."""

from __future__ import annotations

from functools import lru_cache

from backend.config import JiraInstanceSettings, get_settings
from backend.jira.client import JiraClient, JiraError


class JiraRegistry:
    def __init__(self, configs: dict[str, JiraInstanceSettings]) -> None:
        self.configs = configs
        self._clients: dict[str, JiraClient] = {}

    def list_instances(self) -> list[dict[str, str]]:
        return [{"name": item.name, "auth_type": item.auth_type} for item in self.configs.values()]

    def get_client(self, name: str) -> JiraClient:
        key = name.lower()
        if key not in self.configs:
            raise JiraError(f"Unknown Jira instance '{name}'")
        config = self.configs[key]
        missing = []
        if not config.base_url:
            missing.append("BASE_URL")
        if not config.api_token.get_secret_value():
            missing.append("API_TOKEN")
        if config.auth_type == "cloud" and not config.email:
            missing.append("EMAIL")
        if missing:
            raise JiraError(f"Jira instance '{name}' is missing: {', '.join(missing)}")
        if key not in self._clients:
            self._clients[key] = JiraClient(config)
        return self._clients[key]

    async def health(self) -> dict[str, dict]:
        results = {}
        for name in self.configs:
            try:
                results[name] = await self.get_client(name).health()
            except JiraError as exc:
                results[name] = {"status": "error", "message": str(exc), "retryable": False}
        return results


@lru_cache
def get_jira_registry() -> JiraRegistry:
    return JiraRegistry(get_settings().jira_configs())
