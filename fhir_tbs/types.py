from collections.abc import Callable, Coroutine
from typing import Any, Generic, Literal, NotRequired, TypedDict, TypeVar

from aiohttp import web
from fhirpy.base import ResourceProtocol

AnyResourceType = TypeVar("AnyResourceType")


class FilterBy(TypedDict):
    resource_type: str
    filter_parameter: str
    value: str
    comparator: NotRequired[str]
    modifier: NotRequired[str]


SubscriptionHandler = Callable[
    [web.Application, str, list[AnyResourceType], str | None],
    Coroutine[Any, Any, None],
]

SubscriptionType = TypeVar("SubscriptionType", bound=ResourceProtocol)
PayloadContentType = Literal["id-only", "full-resource"]


class SubscriptionCommonDefinition(TypedDict):
    payload_content: NotRequired[PayloadContentType]
    heartbeat_period: NotRequired[int]
    timeout: NotRequired[int]


class SubscriptionDefinition(SubscriptionCommonDefinition):
    filter_by: NotRequired[list[FilterBy]]
    topic: str


class SubscriptionDefinitionPrepared(TypedDict):
    filter_by: NotRequired[list[FilterBy]]
    topic: str

    payload_content: PayloadContentType
    heartbeat_period: int
    timeout: int


class SubscriptionDefinitionWithHandler(Generic[AnyResourceType], SubscriptionDefinition):
    handler: SubscriptionHandler[AnyResourceType]
    webhook_id: NotRequired[str]


class SubscriptionInfo(TypedDict):
    status: str
    token: str | None


class SubscriptionEvent(Generic[AnyResourceType], TypedDict):
    reference: str
    included_resources: list[AnyResourceType]
    timestamp: str | None
    event_number: int
