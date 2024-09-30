from collections.abc import AsyncGenerator

import fhirpy_types_r5 as r5
from aidbox_python_sdk.sdk import SDK
from fhirpy import AsyncFHIRClient

from .implementation import tbs_ctx_factory
from .types import SubscriptionDefinition


def r5_tbs_ctx_factory(
    sdk: SDK,
    aidbox_public_url: str,
    fhir_client: AsyncFHIRClient,
    subscriptions: list[SubscriptionDefinition],
) -> AsyncGenerator[None, None]:
    return tbs_ctx_factory(
        sdk,
        aidbox_public_url,
        fhir_client,
        r5.Bundle,
        r5_build_subscription,
        subscriptions,
    )


def r5_build_subscription(
    name: str, webhook_url: str, token: str, subscription: SubscriptionDefinition
) -> r5.Subscription:
    return r5.Subscription(
        status="requested",
        reason=f"SDK-generated subscription for {name}",
        topic=subscription["topic"],
        channelType=r5.Coding(
            system="http://terminology.hl7.org/CodeSystem/subscription-channel-type",
            code="rest-hook",
        ),
        content="id-only",
        # maxCount must be 1
        maxCount=1,
        heartbeatPeriod=20,
        timeout=60,
        endpoint=webhook_url,
        parameter=[r5.SubscriptionParameter(name="X-Api-Key", value=token)],
    )
