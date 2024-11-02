from collections.abc import Callable, Coroutine
from typing import Any, Generic, Literal, NotRequired, Protocol, TypedDict, TypeVar

from aiohttp import web
from fhirpy import AsyncFHIRClient
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


class SubscriptionDefinition(Generic[AnyResourceType], SubscriptionCommonDefinition):
    handler: SubscriptionHandler[AnyResourceType]
    filter_by: list[FilterBy]
    topic: str
    webhook_id: NotRequired[str]


class SubscriptionDefinitionPrepared(Generic[AnyResourceType], TypedDict):
    filter_by: list[FilterBy]
    topic: str
    
    payload_content: PayloadContentType
    heartbeat_period: int
    timeout: int


class SubscriptionInfo(TypedDict):
    status: str
    token: str | None


class SubscriptionEvent(Generic[AnyResourceType], TypedDict):
    reference: str
    included_resources: list[AnyResourceType]
    timestamp: str | None
    event_number: int


class VersionedClientProtocol(Generic[SubscriptionType, AnyResourceType], Protocol):
    @classmethod
    def build_subscription(
        cls: "VersionedClientProtocol",
        webhook_id: str,
        webhook_url: str,
        webhook_token: str | None,
        subscription: SubscriptionDefinitionPrepared[AnyResourceType],
    ) -> SubscriptionType: ...

    @classmethod
    async def fetch_subscription(
        cls: "VersionedClientProtocol", fhir_client: AsyncFHIRClient, webhook_url: str
    ) -> SubscriptionType | None: ...

    # TODO: some clients don't support $event, make it optional!
    @classmethod
    async def fetch_subscription_events(
        cls: "VersionedClientProtocol",
        fhir_client: AsyncFHIRClient,
        subscription: SubscriptionType,
        since: int | None,
        until: int | None,
    ) -> list[SubscriptionEvent[AnyResourceType]]: ...

    @classmethod
    def extract_subscription_info(
        cls: "VersionedClientProtocol", subscription: SubscriptionType
    ) -> SubscriptionInfo: ...

    @classmethod
    def extract_subscription_events_from_bundle(
        cls: "VersionedClientProtocol",
        bundle_data: dict,
    ) -> list[SubscriptionEvent[AnyResourceType]]: ...
