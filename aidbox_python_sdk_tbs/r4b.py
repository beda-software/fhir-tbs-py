from collections.abc import AsyncGenerator
from typing import Any

import fhirpy_types_r4b as r4b
from aidbox_python_sdk.sdk import SDK
from fhirpy import AsyncFHIRClient
from fhirpy.base.utils import encode_params

from .implementation import tbs_ctx_factory
from .types import SubscriptionDefinition


def r4b_tbs_ctx_factory(
    sdk: SDK,
    aidbox_public_url: str,
    fhir_client: AsyncFHIRClient,
    subscriptions: list[SubscriptionDefinition],
) -> AsyncGenerator[None, None]:
    return tbs_ctx_factory(
        sdk,
        aidbox_public_url,
        fhir_client,
        r4b.Bundle,
        r4b_build_subscription,
        subscriptions,
    )


def r4b_build_subscription(
    name: str, webhook_url: str, token: str, subscription: SubscriptionDefinition
) -> r4b.Subscription:
    return r4b.Subscription(
        meta=r4b.Meta(
            profile=[
                "http://hl7.org/fhir/uv/subscriptions-backport/StructureDefinition/backport-subscription"
            ]
        ),
        reason=f"SDK-generated subscription for {name}",
        status="requested",
        channel=r4b.SubscriptionChannel(
            payload="application/fhir+json",
            payload__ext=r4b.Element(
                extension=[
                    r4b.Extension(
                        url="http://hl7.org/fhir/uv/subscriptions-backport/StructureDefinition/backport-payload-content",
                        valueCode="id-only",
                    )
                ],
            ),
            type="rest-hook",
            endpoint=webhook_url,
            header=[f"X-Api-Key: {token}"],
            extension=[
                # maxCount must be 1
                r4b.Extension(
                    url="http://hl7.org/fhir/uv/subscriptions-backport/StructureDefinition/backport-max-count",
                    valuePositiveInt=1,
                ),
                r4b.Extension(
                    url="http://hl7.org/fhir/uv/subscriptions-backport/StructureDefinition/backport-heartbeat-period",
                    valuePositiveInt=20,
                ),
                r4b.Extension(
                    url="http://hl7.org/fhir/uv/subscriptions-backport/StructureDefinition/backport-timeout",
                    valuePositiveInt=60,
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


def _build_filter_criteria(subscription: SubscriptionDefinition) -> str:
    params: dict[str, Any] = {}

    resource_type = None

    for f in subscription["filterBy"]:
        if not resource_type:
            resource_type = f["resourceType"]
        elif resource_type != f["resourceType"]:
            raise NotImplementedError("Only one resource type is supported for filters")

        param_name = f["filterParameter"]
        if "modifier" in f:
            param_name = f'{f["filterParameter"]}:{f['modifier']}'
        param_value = f["value"]
        if "comparator" in f:
            param_value = f'{f["comparator"]}{f["value"]}'

        params[param_name] = param_value

    if not resource_type:
        raise TypeError("At least one filterBy is required for AidboxSubscription")

    return f"{resource_type}?{encode_params(params)}"
