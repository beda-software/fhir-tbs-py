# fhir-tbs-py

Topic-based subscription extension for python aiohttp web applications.

**Features**:
- Automatically created webhook aiohttp handlers based on definitions
- Unified R4B/R5 API for automatic registration (managed subscriptions)
- Optional managed subscriptions
- Optional authentication using `X-Api-Key`
- `id-only`/`full-resource` support

## Install

Install `fhir-tbs[r4b]` or `fhir-tbs[r5]` using poetry/pipenv/pip.

## Usage

1. Instantiate R4BTBS/R5TBS class with optionally passing predefined subscriptions using `subscriptions` arg and `subscription_defaults` with default subscription parameters (e.g. `payload_content`, `timeout` or `heartbeat_period`):
    ```python
    tbs = R4BTBS(subscription_defaults={"payload_content": "full-resource"})
    ```
2. Define subscriptions using decorator `tbs.define`:
    ```python
    @tbs.define(
        topic="https://example.com/SubscriptionTopic/new-appointment-event",
        filter_by=[
            {
                "resource_type": "Appointment",
                "filter_parameter": "status",
                "value": "booked"
            }
        ],
        webhook_id="new-appointment"
    )
    async def new_appointment_handler(
        app: web.Application,
        reference: str,
        _included_resources: list[r4b.AnyResource],
        _timestamp: str | None,
    ) -> None:
        logging.info("New appointment %s", reference)
    ```
3. Invoke `setup_tbs` on app initialization passing needed parameters (see specification below):
    ```python
    setup_tbs(app, tbs, webhook_path_prefix="webhook")
    ```

### Specification

**fhir_tbs.r4b.R4BTBS**/**fhir_tbs.r5.R5TBS**
- subscriptions (*list[fhir_tbs.SubscriptionDefinitionWithHandler]*, optional) - predefined list of subscriptions.
- subscription_defaults (optional) - default parameters for all subscription definitions.
    - payload_content (*str*, optional): `id-only`/`full-resource` (default is `id-only`)
    - timeout (*int*, optional): default is `60`
    - heartbeat_period (*int*, optional): default is `20`


**tbs_instance.define**
- topic (*str*): URL of SubscriptionTopic to subscribe.
- webhook_id (optional): Optional webhook id that will be part of webhook URL.
- filter_by (*list[FilterBy]*, optional): Optional list of filters applied to topic.
- payload_content (*str*, optional): `id-only`/`full-resource` (default is `id-only`)
- timeout (*int*, optional): default is `60`
- heartbeat_period (*int*, optional): default is `20`

**setup_tbs**
- app (*web.Application*): aiohttp application.
- tbs (*R4BTBS*/*R5TBS*): TBS class instance.
- webhook_path_prefix (*str*): Prefix for the generated aiohttp routes.
- webhook_token (*str*, optional): The authorization token that is checked in X-Api-Token header.
- manage_subscriptions (*bool*, optional): The flag that indicates whether subscription registration/population should be enabled.
- handle_delivery_errors (*bool*, optional): WIP The flag that indicated whether subscription delivery errors (e.g. broken connection or missing events) should be handled.
- app_url (*str*, optional): Application url that is used when `manage_subscriptions`/`handle_delivery_errors` are set.
- get_fhir_client (*Callable[[web.Application], AsyncFHIRClient]*, optional): Getter for web.Application that returns AsyncFHIRClient that further used when `manage_subscriptions`/`handle_delivery_errors` are set.

### Examples

#### General example

Create `subscriptions.py` with the following content:

```python
import logging

from fhirpy import AsyncFHIRClient
import fhirpy_types_r4b as r4b
from fhir_tbs import SubscriptionDefinitionWithHandler
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


tbs = R4BTBS()

@tbs.define(
    topic="https://example.com/SubscriptionTopic/new-appointment-event",
    filter_by=[
        {
            "resource_type": "Appointment",
            "filter_parameter": "status",
            "value": "booked"
        }
    ],
    webhook_id="new-appointment"
)
async def new_appointment_handler(
    app: web.Application,
    reference: str,
    _included_resources: list[r4b.AnyResource],
    _timestamp: str | None,
) -> None:
    logging.info("New appointment %s", reference)


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

