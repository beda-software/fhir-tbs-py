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

The package is responsible for adding new routes per subscription and subscribing to the subscriptions (optional).
For this purpose [https://docs.aiohttp.org/en/stable/web_advanced.html#cleanup-context](aiohttp cleanup_ctx) is used.
The package provides `ctx_factory` that should be used for creating `cleanup_ctx`. Inside you `cleanup_ctx` all the application variables can be accessed that earlier were initialized using `on_startup/`cleanup_ctx`.


Create `subscriptions.py` with the following content:

```python
import logging
from collections.abc import AsyncGenerator

from fhirpy import AsyncFHIRClient
import fhirpy_types_r4b as r4b
from fhir_tbs import SubscriptionDefinition
from fhir_tbs.r4b import R4BTBS
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


tbs = R4BTBS(subscriptions=subscriptions)


def tbs_ctx(app: web.Application) -> AsyncGenerator[None, None]:
    return tbs.ctx_factory(
        app,
        app_url="http://app:8080",
        webhook_path_prefix="webhook",
        subscription_fhir_client=app[ak.fhir_client_key]
    )


def create_app() -> web.Application:
    app = web.Application()
    app[ak.fhir_client_key] = AsyncFHIRClient(...)
    app.cleanup_ctx.append(tbx_ctx)

```




## Using in aidbox-python-sdk for external subscriptions


```python
external_webhook_path_prefix_parts = ["external-webhook"]

external_tbs = R4BTBS(subscriptions=subscriptions)

def setup_external_tbs(app: web.Application) -> None:
    return setup_tbs(
        app,
        external_tbs,
        app_url="http://aidbox.example.com",
        webhook_prefix_path="/".join(external_webhook_path_prefix_parts),
        subscription_fhir_client=app[ak.fhir_client_key],
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
        return web.Response(
            body=await response.text(),
            status=response.status,
            content_type=response.content_type,
        )


def create_app() -> web.Application:
    app = web.Application()
    app[ak.fhir_client_key] = AsyncFHIRClient(...)

    setup_external_tbs(app)

```

