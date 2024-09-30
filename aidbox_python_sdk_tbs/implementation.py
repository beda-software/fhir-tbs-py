from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine
from typing import Any, Protocol, TypeVar, cast
from uuid import uuid4

from aidbox_python_sdk.sdk import SDK
from aidbox_python_sdk.types import SDKOperation, SDKOperationRequest
from aiohttp import web
from fhirpy import AsyncFHIRClient
from fhirpy.base import ResourceProtocol

from .types import SubscriptionDefinition


class BundleEntryRequestProtocol(Protocol):
    url: str


class BundleEntryProtocol(Protocol):
    request: BundleEntryRequestProtocol | None = None
    resource: ResourceProtocol | None = None


class BundleProtocol(ResourceProtocol, Protocol):
    entry: list[BundleEntryProtocol] | None = None


ResourceType = TypeVar("ResourceType", bound=ResourceProtocol)
BundleType = TypeVar("BundleType", bound=BundleProtocol)
SubscriptionType = TypeVar("SubscriptionType", bound=ResourceProtocol)


async def tbs_ctx_factory(  # noqa: PLR0913
    sdk: SDK,
    aidbox_public_url: str,
    fhir_client: AsyncFHIRClient,
    bundle_cls: type[ResourceType],
    build_subscription: Callable[[str, str, str, SubscriptionDefinition], SubscriptionType],
    subscriptions: list[SubscriptionDefinition],
) -> AsyncGenerator[None, None]:
    created_subscriptions: list[SubscriptionType] = []
    for subscription in subscriptions:
        handler = subscription["handler"]
        handler_name = f"{handler.__module__}.{handler.__name__}"

        webhook_path_parts = ["webhook", handler_name]
        webhook_path = "/".join(webhook_path_parts)
        webhook_url = f"{aidbox_public_url}/{webhook_path}"
        token = str(uuid4())

        await cleanup_subscriptions_by_url(
            fhir_client, cast(type[BundleProtocol], bundle_cls), webhook_url
        )

        sdk.operation(["POST"], webhook_path_parts, public=True)(
            _wrapper(
                fhir_client,
                cast(type[BundleProtocol], bundle_cls),
                token,
                handler,
            )
        )

        created_subscriptions.append(
            await fhir_client.create(
                build_subscription(handler_name, webhook_url, token, subscription)
            )
        )
    yield

    for created_subscription in created_subscriptions:
        await fhir_client.delete(created_subscription)


async def cleanup_subscriptions_by_url(
    fhir_client: AsyncFHIRClient, bundle_cls: type[BundleType], url: str
) -> None:
    bundle = bundle_cls(**(await fhir_client.resources("Subscription").search(url=url).fetch_raw()))
    entries = bundle.entry or []

    for entry in entries:
        resource = entry.resource
        assert resource

        await fhir_client.delete(resource)


def _wrapper(
    fhir_client: AsyncFHIRClient,
    bundle_cls: type[BundleType],
    token: str,
    handler: Callable[[web.Application, Any], Coroutine[Any, Any, None]],
) -> Callable[[SDKOperation, SDKOperationRequest], Awaitable[web.Response]]:
    async def wrapped_handler(_op: SDKOperation, request: SDKOperationRequest) -> web.Response:
        if request["headers"].get("x-api-key") != token:
            raise web.HTTPUnauthorized()

        subscription_bundle = bundle_cls(**request["resource"])
        assert subscription_bundle.entry

        # The first entry is SubscriptionStatus, the second entry contains request only
        assert len(subscription_bundle.entry) <= 2  # noqa: PLR2004

        for entry in subscription_bundle.entry[1:]:
            assert entry.request
            url = entry.request.url
            url_parts = url.split("/")
            resource_type, resource_id = url_parts[-2], url_parts[-1]

            resource_bundle = bundle_cls(
                **(await fhir_client.resources(resource_type).search(_id=resource_id).fetch_raw())
            )
            assert resource_bundle.entry
            assert resource_bundle.entry[0].resource
            resource = resource_bundle.entry[0].resource

            await handler(request["app"], resource)

        return web.json_response({})

    return wrapped_handler
