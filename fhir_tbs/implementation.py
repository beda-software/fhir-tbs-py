from collections.abc import AsyncGenerator, Awaitable, Callable
from uuid import uuid4

from aiohttp import web
from fhirpy import AsyncFHIRClient

from .types import (
    AnyResourceType,
    PayloadContentType,
    SubscriptionDefinition,
    SubscriptionHandler,
    VersionedClientProtocol,
)


async def tbs_ctx_factory(  # noqa: PLR0913
    client: VersionedClientProtocol,
    app: web.Application,
    app_url: str,
    webhook_path_prefix: str,
    subscriptions: list[SubscriptionDefinition[AnyResourceType]],
    *,
    subscription_fhir_client: AsyncFHIRClient | None = None,
    subscription_payload_content: PayloadContentType = "id-only",
    webhook_token: str | None = None,
) -> AsyncGenerator[None, None]:
    for subscription in subscriptions:
        handler = subscription["handler"]
        webhook_id = subscription.get("webhook_id")
        if not webhook_id:
            if not subscription_fhir_client:
                raise TypeError("webhook_id should be set for manual subscriptions")
            webhook_id = f"{handler.__module__}.{handler.__name__}"
        webhook_path_parts = [webhook_path_prefix.strip("/"), webhook_id]
        webhook_path = "/".join(webhook_path_parts)
        webhook_url = f"{app_url.rstrip('/')}/{webhook_path}"

        if subscription_fhir_client:
            existing_subscription = await client.fetch_subscription(
                subscription_fhir_client, webhook_url
            )
            if existing_subscription:
                existing_subscription_info = client.extract_subscription_info(existing_subscription)
                if existing_subscription_info["status"] == "active":
                    webhook_token = existing_subscription_info["token"]
                else:
                    await subscription_fhir_client.delete(existing_subscription)
                    existing_subscription = None

            if not existing_subscription:
                await subscription_fhir_client.create(
                    client.build_subscription(
                        webhook_id,
                        webhook_url,
                        webhook_token,
                        subscription_payload_content,
                        subscription,
                    )
                )

        app.add_routes(
            [
                web.post(
                    f"/{webhook_path}",
                    _wrapper(
                        client,
                        handler,
                        webhook_token,
                    ),
                )
            ]
        )

    yield


def _wrapper(
    client: VersionedClientProtocol,
    handler: SubscriptionHandler,
    token: str | None,
) -> Callable[[web.Request], Awaitable[web.Response]]:
    async def wrapped_handler(request: web.Request) -> web.Response:
        if token is not None and request.headers.get("x-api-key") != token:
            raise web.HTTPUnauthorized()

        data = await request.json()
        events = client.extract_subscription_events_from_bundle(data)

        assert len(events) <= 1, "Only one event can be passed into handler"

        for event in events:
            await handler(
                request.app, event["reference"], event["included_resources"], event["timestamp"]
            )

        return web.json_response(data)

    return wrapped_handler
