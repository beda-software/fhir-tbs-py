# fhir-tbs-py

Topic-based subscription extension for python aiohttp web applications

**Features**:
- Unified R4B/R5 API for automatic registration
- Optional automatic registration
- Optional authentication using X-Api-Key
- `id-only`/`full-resource` support

## Install

Install `fhir-tbs[r4b]` or `fhir-tbs[r5]` using poetry/pipenv/pip.

## Usage

Create `subscriptions.py` with the following content:

```python
import logging
from collections.abc import AsyncGenerator

from fhirpy import AsyncFHIRClient
import fhirpy_types_r4b as r4b
from fhir_tbs import SubscriptionDefinition
from fhir_tbs.r4b import r4b_tbs_ctx_factory
from aiohttp import web

# Make sure that app has fhir_client_key
fhir_client_key = web.AppKey("fhir_client_key", AsyncFHIRClient)


async def new_appointment_sub(
    app: web.Application,
    appointment_ref: str,
    _included_resources: list[r4b.AnyResource],
    _timestamp: str
) -> None:
    fhir_client = app[fhir_client_key]
    appointment = r4b.Appointment(**(await fhir_client.get(appointment_ref)))
    logging.error("New appointment %s", appointment.model_dump())


subscriptions: list[SubscriptionDefinition[r4b.AnyResource]] = [
    {
        "topic": "https://example.com/SubscriptionTopic/new-appointment-event",
        "handler": new_appointment_sub,
        "filterBy": [
            {"resourceType": "Appointment", "filterParameter": "status", "value": "booked"}
        ],
    },
]


def tbs_ctx(app: web.Application) -> AsyncGenerator[None, None]:
    return r4b_tbs_ctx_factory(
        app,
        "http://app:8080",
        "webhook",
        subscriptions,
        subscription_fhir_client=app[fhir_client_key],
    )
```


Add `tbs_ctx` to `app.cleanup_ctx`.


## Using in aidbox-python-sdk for external subscriptions


```python
external_webhook_path_prefix_parts = ["external-webhook"]


def external_tbs_ctx(app: web.Application) -> AsyncGenerator[None, None]:
    return r4b_tbs_ctx_factory(
        app,
        config.aidbox_public_url,
        "/".join(external_webhook_path_prefix_parts),
        subscriptions,
        subscription_fhir_client=app[ak.fhir_client_keey],
    )


@sdk.operation(
    methods=["POST"],
    path=[*external_webhook_path_prefix_parts, {"name": "webhook-name"}],
    public=True,
)
async def external_webhook_proxy_op(
    _operation: SDKOperation, request: SDKOperationRequest
) -> web.Response:
    session = request["app"][ak.session]
    app_url = str(request["app"][ak.settings].APP_URL).rstrip("/")
    webhook_name = request["route-params"]["webhook-name"]
    path = "/".join([*external_webhook_path_prefix_parts, webhook_name])
    token = request["headers"].get("x-api-key")

    async with session.post(
        f"{app_url}/{path}",
        headers={"X-Api-Key": token} if token else {},
        json=request["resource"],
    ) as response:
        return web.json_response(await response.json(), status=response.status)
```

