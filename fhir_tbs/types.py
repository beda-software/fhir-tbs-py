from collections.abc import Callable, Coroutine
from typing import Any, NotRequired, TypedDict

from aiohttp import web


class FilterBy(TypedDict):
    resourceType: str
    filterParameter: str
    value: str
    comparator: NotRequired[str]
    modifier: NotRequired[str]


SubscriptionHandler = Callable[[web.Application, str, str | None], Coroutine[Any, Any, None]]


class SubscriptionDefinition(TypedDict):
    handler: SubscriptionHandler
    filterBy: list[FilterBy]
    topic: str
