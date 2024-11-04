# fhir-tbs-py

Topic-based subscription extension for python aiohttp web applications

**Features**:
- Unified R4B/R5 API for automatic registration (managed subscriptions)
- Optional managed subscriptions
- Optional authentication using X-Api-Key
- `id-only`/`full-resource` support

## Install

Install `fhir-tbs[r4b]` or `fhir-tbs[r5]` using poetry/pipenv/pip.

## Usage

1. Define subscriptions using `fhir_tbs.SubscriptionDefinition` type.
2. Instantiate R4BTBS/R5TBS class with predefined subscriptions.
    - `tbs = R4BTBS(subscriptions=subscriptions)`
    - `subscription_defaults` can be optionally passed to define defaults for managed subscriptions
        - `payload_content` - `id-only`/`full-resource` (default is `id-only`)
        - `timeout` - default is 60
        - `heartbeat_period` - default is 20
3. Invoke `setup_tbs(app, tbs, webhook_path_prefix="webhook")` on app initialization passing needed parameters:
    - The package supports managed and non-managed subscriptions through `manage_subscriptions` flag (default is False). 
        Managed subscriptions requires `app_url` and `get_fhir_client` args to be set.
    - Also in the future the package will be responsible for handling delivery errors, in that case
        `handle_delivery_errors` should be set to `True` and it also requires `app_url` and `get_fhir_client` args to be set.
    - Specify `webhook_token` for required auth token that should be passed via `X-Api-Key` header

### Specification

TBD

### Examples

#### General example

Create `subscriptions.py` with the following content:

```python
import logging

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
    included_resources: list[r4b.AnyResource],
    _timestamp: str
) -> None:
    fhir_client = app[fhir_client_key]
    # For id-only use fhir_client to fetch the resource
    appointment = r4b.Appointment(**(await fhir_client.get(appointment_ref)))
    # For full-resource find in in included resources by reference (straightforward example) 
    appointment = [
        resource for resource in included_resources 
        if appointment_ref == f"{resource.resourceType}/{resource.id}"
    ][0]

    logging.info("New appointment %s", appointment.model_dump())


subscriptions: list[SubscriptionDefinition[r4b.AnyResource]] = [
    {
        "topic": "https://example.com/SubscriptionTopic/new-appointment-event",
        "handler": new_appointment_sub,
        "filter_by": [
            {"resource_type": "Appointment", "filter_parameter": "status", "value": "booked"}
        ],
    },
]


tbs = R4BTBS(subscriptions=subscriptions)


def create_app() -> web.Application:
    app = web.Application()
    app[fhir_client_key] = AsyncFHIRClient(...)
    setup_tbs(
        app, 
        tbs,
        webhook_path_prefix="webhook",
        app_url="http://app:8080",
        get_fhir_client=lambda app: app[fhir_client_key],
        manage_subscriptions=True,
        handle_delivery_errors=True
    )

```


#### Using in aidbox-python-sdk for external subscriptions


```python
external_webhook_path_prefix_parts = ["external-webhook"]

external_tbs = R4BTBS(subscriptions=subscriptions)

def setup_external_tbs(app: web.Application) -> None:
    setup_tbs(
        app,
        external_tbs,
        webhook_prefix_path="/".join(external_webhook_path_prefix_parts),
        app_url="http://aidbox.example.com",
        get_fhir_client=lambda app: app[fhir_client_key],
        manage_subscriptions=True,
        handle_delivery_errors=True
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
    app[fhir_client_key] = AsyncFHIRClient(...)

    setup_external_tbs(app)

```

