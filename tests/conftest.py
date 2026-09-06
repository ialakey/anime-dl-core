"""Общие приспособления для тестов: загрузка фикстур и http-клиент-заглушка."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

import pytest

from anime_players.http import DEFAULT_USER_AGENT, Response

FIXTURES = Path(__file__).parent / "fixtures"

RouteValue = Union[str, Response, Callable[[str], Response]]


def fixture(name: str) -> str:
    """Содержимое файла из ``tests/fixtures``."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str) -> Any:
    return json.loads(fixture(name))


class FakeClient:
    """Заглушка вместо :class:`anime_players.http.HttpClient`.

    Маршруты задаются подстрокой url: первый подошедший и отдаётся.
    """

    def __init__(self, routes: Mapping[str, RouteValue], *, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.routes: Dict[str, RouteValue] = dict(routes)
        self.user_agent = user_agent
        self.calls: List[Dict[str, Any]] = []
        self.closed = False

    # -- интерфейс HttpClient -----------------------------------------
    def get(self, url: str, **kwargs: Any) -> Response:
        return self._respond("GET", url, kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self._respond("POST", url, kwargs)

    def resolve_redirect(self, url: str, **kwargs: Any) -> str:
        response = self._respond("GET", url, kwargs)
        return response.headers.get("Location", url)

    def close(self) -> None:
        self.closed = True

    # -- внутреннее ----------------------------------------------------
    def _respond(self, method: str, url: str, kwargs: Dict[str, Any]) -> Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        for pattern, value in self.routes.items():
            if pattern in url:
                if callable(value):
                    return value(url)
                if isinstance(value, Response):
                    return value
                return Response(200, value, url)
        raise AssertionError(f"В тесте нет маршрута для {method} {url}")

    def last_call(self, method: Optional[str] = None) -> Dict[str, Any]:
        for call in reversed(self.calls):
            if method is None or call["method"] == method:
                return call
        raise AssertionError("Запросов не было")


@pytest.fixture
def make_client():
    """Фабрика :class:`FakeClient` для тестов."""

    def _make(routes: Mapping[str, RouteValue]) -> FakeClient:
        return FakeClient(routes)

    return _make


def pytest_collection_modifyitems(config: Any, items: List[Any]) -> None:
    """Живые тесты пропускаются, если не выставлен ANIME_PLAYERS_LIVE=1."""
    if os.environ.get("ANIME_PLAYERS_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="нужен доступ в интернет: ANIME_PLAYERS_LIVE=1")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
