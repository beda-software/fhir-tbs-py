from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TypedDict, TypeVar
from uuid import uuid4

from aiohttp import web
from fhirpy import AsyncFHIRClient
from fhirpy.base import ResourceProtocol

from .types import SubscriptionDefinition, SubscriptionHandler

SubscriptionType = TypeVar("SubscriptionType", bound=ResourceProtocol)
BundleType = TypeVar("BundleType", bound=ResourceProtocol)


class SubscriptionInfo(TypedDict):
    status: str
    token: str | None


class SubscriptionEvent(TypedDict):
    reference: str
    timestamp: str | None
    event_number: int


async def tbs_ctx_factory(
    app: web.Application,
    app_url: str,
    webhook_path_prefix: str,
    fhir_client: AsyncFHIRClient,
    subscriptions: list[SubscriptionDefinition],
    *,
    _build_subscription: Callable[[str, str, str, SubscriptionDefinition], SubscriptionType],
    _fetch_subscription: Callable[[AsyncFHIRClient, str], Awaitable[SubscriptionType | None]],
    _fetch_subscription_events: Callable[
        [AsyncFHIRClient, SubscriptionType, int | None, int | None], Awaitable[list[SubscriptionEvent]]
    ],
    _extract_subscription_info: Callable[[SubscriptionType], SubscriptionInfo],
    _extract_subscription_events_from_bundle: Callable[[dict], list[SubscriptionEvent]],
) -> AsyncGenerator[None, None]:
    for subscription in subscriptions:
        handler = subscription["handler"]
        handler_name = f"{handler.__module__}.{handler.__name__}"

        webhook_path_parts = [webhook_path_prefix.strip("/"), handler_name]
        webhook_path = "/".join(webhook_path_parts)
        webhook_url = f"{app_url.rstrip("/")}/{webhook_path}"

        existing_subscription = await _fetch_subscription(fhir_client, webhook_url)
        if existing_subscription:
            _events = await _fetch_subscription_events(fhir_client, existing_subscription, 0, 0)
            # TODO: handle them in #1/#2

            existing_subscription_info = _extract_subscription_info(existing_subscription)
            if existing_subscription_info["status"] == "active":
                token = existing_subscription_info["token"]
            else:
                await fhir_client.delete(existing_subscription)
                existing_subscription = None

        if not existing_subscription:
            token = str(uuid4())
            await fhir_client.create(
                _build_subscription(handler_name, webhook_url, token, subscription)
            )

        app.add_routes(
            [
                web.post(
                    f"/{webhook_path}",
                    _wrapper(
                        handler,
                        token,
                        _extract_subscription_events_from_bundle=_extract_subscription_events_from_bundle,
                    ),
                )
            ]
        )

    yield


def _wrapper(
    handler: SubscriptionHandler,
    token: str | None,
    *,
    _extract_subscription_events_from_bundle: Callable[[dict], list[SubscriptionEvent]],
) -> Callable[[web.Request], Awaitable[web.Response]]:
    async def wrapped_handler(request: web.Request) -> web.Response:
        if token is not None and request.headers.get("x-api-key") != token:
            raise web.HTTPUnauthorized()

        events = _extract_subscription_events_from_bundle(await request.json())
        assert len(events) <= 1, "Only one event can be passed into handler"

        for event in events:
            await handler(
                request.app, _extract_local_reference(event["reference"]), event["timestamp"]
            )

        return web.json_response({})

    return wrapped_handler


def _extract_local_reference(reference: str) -> str:
    """
    >>> _extract_local_reference("http://localhost/fhir/Patient/test")
    'Patient/test'
    """
    return "/".join(reference.split("/")[-2:])
