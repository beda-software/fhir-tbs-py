from collections.abc import AsyncGenerator
from typing import Any

import fhirpy_types_r4b as r4b
from aiohttp import web
from fhirpy import AsyncFHIRClient
from fhirpy.base.utils import encode_params
from pydantic import BaseModel

from .implementation import tbs_ctx_factory
from .types import (
    SubscriptionCommonDefinition,
    SubscriptionDefinition,
    SubscriptionDefinitionPrepared,
    SubscriptionEvent,
    SubscriptionInfo,
    VersionedClientProtocol,
)
from .utils import extract_relative_reference


def r4b_tbs_ctx_factory(  # noqa: PLR0913
    app: web.Application,
    app_url: str,
    webhook_path_prefix: str,
    subscriptions: list[SubscriptionDefinition[r4b.AnyResource]],
    *,
    subscription_fhir_client: AsyncFHIRClient | None = None,
    subscription_defaults: SubscriptionCommonDefinition | None = None,
    webhook_token: str | None = None,
) -> AsyncGenerator[None, None]:
    return tbs_ctx_factory(
        R4BClient,
        app,
        app_url,
        webhook_path_prefix,
        subscriptions,
        subscription_fhir_client=subscription_fhir_client,
        subscription_defaults=subscription_defaults,
        webhook_token=webhook_token,
    )


class R4BClient(VersionedClientProtocol[r4b.Subscription, r4b.AnyResource]):
    @classmethod
    async def fetch_subscription(
        cls: type["R4BClient"], fhir_client: AsyncFHIRClient, webhook_url: str
    ) -> r4b.Subscription | None:
        return await fhir_client.resources(r4b.Subscription).search(url=webhook_url).first()

    @classmethod
    async def fetch_subscription_events(
        cls: type["R4BClient"],
        fhir_client: AsyncFHIRClient,
        subscription: r4b.Subscription,
        since: int | None,
        until: int | None,
    ) -> list[SubscriptionEvent[r4b.AnyResource]]:
        bundle_data = await fhir_client.execute(
            f"Subscription/{subscription.id}/$events",
            method="GET",
            params={"eventsSinceNumber": since, "eventsUntilNumber": until},
        )
        return cls.extract_subscription_events_from_bundle(bundle_data)

    @classmethod
    def extract_subscription_info(
        cls: type["R4BClient"], subscription: r4b.Subscription
    ) -> SubscriptionInfo:
        token = None
        headers = subscription.channel.header or []
        for header in headers:
            if header.lower().startswith("x-api-key"):
                token = header.split(":", 1)[1].strip()

        return {"status": subscription.status, "token": token}

    @classmethod
    def extract_subscription_events_from_bundle(
        cls: type["R4BClient"],
        bundle_data: dict,
    ) -> list[SubscriptionEvent[r4b.AnyResource]]:
        notification_bundle = r4b.Bundle(**bundle_data)
        _extract_relative_references_recursive(notification_bundle)

        assert notification_bundle.entry
        assert notification_bundle.entry[0]
        assert notification_bundle.entry[0].resource
        subscription_status = notification_bundle.entry[0].resource
        assert isinstance(subscription_status, r4b.SubscriptionStatus)

        included_resources_by_reference = {
            f"{entry.resource.resourceType}/{entry.resource.id}": entry.resource
            for entry in notification_bundle.entry[1:]
            if entry.resource
        }

        subscription_events: list[SubscriptionEvent[r4b.AnyResource]] = []

        for event in subscription_status.notificationEvent or []:
            if not event.focus or not event.focus.reference:
                continue
            focus_reference = event.focus.reference
            context_references = [
                ctx.reference for ctx in (event.additionalContext or []) if ctx.reference
            ]

            subscription_events.append(
                {
                    "reference": focus_reference,
                    "included_resources": [
                        included_resources_by_reference[reference]
                        for reference in [*context_references, focus_reference]
                        if reference in included_resources_by_reference
                    ],
                    "timestamp": event.timestamp,
                    "event_number": int(event.eventNumber),
                }
            )

        return subscription_events

    @classmethod
    def build_subscription(
        cls: type["R4BClient"],
        webhook_id: str,
        webhook_url: str,
        webhook_token: str | None,
        subscription: SubscriptionDefinitionPrepared[r4b.AnyResource],
    ) -> r4b.Subscription:
        return r4b.Subscription(
            meta=r4b.Meta(
                profile=[
                    "http://hl7.org/fhir/uv/subscriptions-backport/StructureDefinition/backport-subscription"
                ]
            ),
            reason=f"Autogenerated subscription for {webhook_id}",
            status="requested",
            channel=r4b.SubscriptionChannel(
                payload="application/fhir+json",
                payload__ext=r4b.Element(
                    extension=[
                        r4b.Extension(
                            url="http://hl7.org/fhir/uv/subscriptions-backport/StructureDefinition/backport-payload-content",
                            valueCode=subscription["payload_content"],
                        )
                    ],
                ),
                type="rest-hook",
                endpoint=webhook_url,
                header=[f"X-Api-Key: {webhook_token}"] if webhook_token else None,
                extension=[
                    r4b.Extension(
                        url="http://hl7.org/fhir/uv/subscriptions-backport/StructureDefinition/backport-max-count",
                        # maxCount must be 1
                        valuePositiveInt=1,
                    ),
                    r4b.Extension(
                        url="http://hl7.org/fhir/uv/subscriptions-backport/StructureDefinition/backport-heartbeat-period",
                        valuePositiveInt=subscription["heartbeat_period"],
                    ),
                    r4b.Extension(
                        url="http://hl7.org/fhir/uv/subscriptions-backport/StructureDefinition/backport-timeout",
                        valuePositiveInt=subscription["timeout"],
                    ),
                ],
            ),
            criteria=subscription["topic"],
            criteria__ext=r4b.Element(
                extension=[
                    r4b.Extension(
                        url="http://hl7.org/fhir/uv/subscriptions-backport/StructureDefinition/backport-filter-criteria",
                        valueString=_build_filter_criteria(subscription),
                    )
                ],
            ),
        )


def _build_filter_criteria(subscription: SubscriptionDefinitionPrepared[r4b.AnyResource]) -> str:
    params: dict[str, Any] = {}

    resource_type = None

    for f in subscription["filter_by"]:
        if not resource_type:
            resource_type = f["resource_type"]
        elif resource_type != f["resource_type"]:
            raise NotImplementedError("Only one resource type is supported for filters")

        param_name = f["filter_parameter"]
        if "modifier" in f:
            param_name = f'{f["filter_parameter"]}:{f["modifier"]}'
        param_value = f["value"]
        if "comparator" in f:
            param_value = f'{f["comparator"]}{f["value"]}'

        params[param_name] = param_value

    if not resource_type:
        raise TypeError("At least one filterBy is required for AidboxSubscription")

    return f"{resource_type}?{encode_params(params)}"


def _extract_relative_references_recursive(instance: BaseModel) -> BaseModel:
    if isinstance(instance, r4b.Reference) and instance.reference:
        instance.reference = extract_relative_reference(instance.reference)

        return instance

    for field_name in instance.model_fields:
        field_value = getattr(instance, field_name)
        if isinstance(field_value, list):
            for sub_field in field_value:
                _extract_relative_references_recursive(sub_field)
        if isinstance(field_value, BaseModel):
            _extract_relative_references_recursive(field_value)

    return instance
