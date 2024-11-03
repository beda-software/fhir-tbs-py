from abc import abstractmethod
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Generic, Self

from aiohttp import web
from fhirpy import AsyncFHIRClient

from .types import (
    AnyResourceType,
    SubscriptionCommonDefinition,
    SubscriptionDefinition,
    SubscriptionDefinitionPrepared,
    SubscriptionEvent,
    SubscriptionHandler,
    SubscriptionInfo,
    SubscriptionType,
)


def setup_tbs(  # noqa: PLR0913
    app: web.Application,
    tbs: "AbstractTBS",
    *,
    webhook_path_prefix: str,
    webhook_token: str | None = None,
    manage_subscriptions: bool = False,
    handle_delivery_errors: bool = False,
    app_url: str | None = None,
    get_fhir_client: Callable[[web.Application], AsyncFHIRClient] | None = None,
) -> None:
    """
    Setup TBS routes and manage subscriptions/handle delivery errors

    Args:
        app: aiohttp application.
        webhook_path_prefix: prefix for the generated aiohttp routes.
        manage_subscriptions (optional): the flag that indicates whether
            subscription registration/population should be enabled.
        handle_delivery_errors (optional): WIP the flag that indicated whether
            subscription delivery errors (e.g. broken connection or missing events) should be handled.
        app_url (optional): application url that is used
            when `manage_subscriptions`/`handle_delivery_errors` are set.
        get_fhir_client (optional): getter for web.Application that returns AsyncFHIRClient
            that further used when `manage_subscriptions`/`handle_delivery_errors` are set.

    Returns:
        None
    """

    def ctx(app: web.Application) -> AsyncGenerator[None, None]:
        return tbs._ctx_factory(
            app,
            webhook_path_prefix=webhook_path_prefix,
            webhook_token=webhook_token,
            manage_subscriptions=manage_subscriptions,
            handle_delivery_errors=handle_delivery_errors,
            app_url=app_url,
            get_fhir_client=get_fhir_client,
        )

    app.cleanup_ctx.append(ctx)


class AbstractTBS(Generic[SubscriptionType, AnyResourceType]):
    subscriptions: list[SubscriptionDefinition[AnyResourceType]]
    subscription_defaults: SubscriptionCommonDefinition | None

    def __init__(
        self: Self,
        *,
        subscriptions: list[SubscriptionDefinition[AnyResourceType]] | None = None,
        subscription_defaults: SubscriptionCommonDefinition | None = None,
    ) -> None:
        self.subscriptions = subscriptions or []
        self.subscription_defaults = subscription_defaults

    async def _ctx_factory(  # noqa: PLR0913
        self: Self,
        app: web.Application,
        *,
        webhook_path_prefix: str,
        webhook_token: str | None = None,
        manage_subscriptions: bool = False,
        handle_delivery_errors: bool = False,
        app_url: str | None = None,
        get_fhir_client: Callable[[web.Application], AsyncFHIRClient] | None = None,
    ) -> AsyncGenerator[None, None]:
        subscription_defaults = self.subscription_defaults or {}
        for subscription in self.subscriptions:
            subscription_prepared: SubscriptionDefinitionPrepared[AnyResourceType] = {
                "payload_content": subscription.get(
                    "payload_content",
                    subscription_defaults.get("payload_content", "id-only"),
                ),
                "timeout": subscription.get("timeout", subscription_defaults.get("timeout", 20)),
                "heartbeat_period": subscription.get(
                    "heartbeat_period",
                    subscription_defaults.get("heartbeat_period", 60),
                ),
                "filter_by": subscription["filter_by"],
                "topic": subscription["topic"],
            }

            handler = subscription["handler"]
            webhook_id = subscription.get("webhook_id")
            if not webhook_id:
                if not manage_subscriptions:
                    raise TypeError("`webhook_id` should be set for non-managed subscriptions")
                webhook_id = f"{handler.__module__}.{handler.__name__}"
            webhook_path_parts = [webhook_path_prefix.strip("/"), webhook_id]
            webhook_path = "/".join(webhook_path_parts)

            if manage_subscriptions or handle_delivery_errors:
                if not get_fhir_client:
                    raise TypeError(
                        "`get_fhir_client` must be provided to use `manage_subscriptions`/`handle_delivery_errors`"
                    )
                if not app_url:
                    raise TypeError(
                        "`app_url` must be provided to use `manage_subscriptions`/`handle_delivery_errors`"
                    )

                fhir_client = get_fhir_client(app)
                webhook_url = f"{app_url.rstrip('/')}/{webhook_path}"
                existing_subscription = await self.fetch_subscription(fhir_client, webhook_url)

                if manage_subscriptions:
                    if existing_subscription:
                        existing_subscription_info = self.extract_subscription_info(
                            existing_subscription
                        )

                        if existing_subscription_info["status"] == "active":
                            webhook_token = existing_subscription_info["token"]
                        else:
                            await fhir_client.delete(existing_subscription)
                            existing_subscription = None

                    if not existing_subscription:
                        await fhir_client.create(
                            self.build_subscription(
                                webhook_id,
                                webhook_url,
                                webhook_token,
                                subscription_prepared,
                            )
                        )

                if handle_delivery_errors:
                    # TODO: not implemented
                    # TODO: See #1/#2/#3
                    pass

            app.add_routes(
                [
                    web.post(
                        f"/{webhook_path}",
                        self._wrapper(handler, webhook_token),
                    )
                ]
            )

        yield

    def _wrapper(
        self: Self,
        handler: SubscriptionHandler,
        token: str | None,
    ) -> Callable[[web.Request], Awaitable[web.Response]]:
        async def wrapped_handler(request: web.Request) -> web.Response:
            if token is not None and request.headers.get("x-api-key") != token:
                raise web.HTTPUnauthorized()

            data = await request.json()
            events = self.extract_subscription_events_from_bundle(data)

            assert len(events) <= 1, "Only one event can be passed into handler"

            for event in events:
                await handler(
                    request.app, event["reference"], event["included_resources"], event["timestamp"]
                )

            return web.json_response(data)

        return wrapped_handler

    @classmethod
    @abstractmethod
    async def fetch_subscription(
        cls: type["AbstractTBS"], fhir_client: AsyncFHIRClient, webhook_url: str
    ) -> SubscriptionType | None: ...

    @classmethod
    @abstractmethod
    async def fetch_subscription_events(
        cls: type["AbstractTBS"],
        fhir_client: AsyncFHIRClient,
        subscription: SubscriptionType,
        since: int | None,
        until: int | None,
    ) -> list[SubscriptionEvent[AnyResourceType]]: ...

    @classmethod
    @abstractmethod
    def build_subscription(
        cls: type["AbstractTBS"],
        webhook_id: str,
        webhook_url: str,
        webhook_token: str | None,
        subscription: SubscriptionDefinitionPrepared[AnyResourceType],
    ) -> SubscriptionType: ...

    @classmethod
    @abstractmethod
    def extract_subscription_info(
        cls: type["AbstractTBS"], subscription: SubscriptionType
    ) -> SubscriptionInfo: ...

    @classmethod
    @abstractmethod
    def extract_subscription_events_from_bundle(
        cls: type["AbstractTBS"],
        bundle_data: dict,
    ) -> list[SubscriptionEvent[AnyResourceType]]: ...
