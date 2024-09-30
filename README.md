# aidbox-python-sdk-tbs

Topic-based subscription extension for Aidbox SDK for python

## Install

Install `aidbox-python-sdk-tbs[r4b]` or `aidbox-python-sdk-tbs[r5]` using poetry/pipenv/pip.

## Usage

Create `app/app_keys.py` with the following context:

```python
from aidbox_python_sdk.app_keys import client, sdk, settings
from aiohttp import web
from fhirpy import AsyncFHIRClient

fhir_client: web.AppKey[AsyncFHIRClient] = web.AppKey("fhir_client", AsyncFHIRClient)

__all__ = ["fhir_client", "client", "sdk", "settings"]
```

Create `app/subscriptions.py` with the following content:

```python
import logging
from collections.abc import AsyncGenerator

import fhirpy_types_r4b as r4b
from aidbox_python_sdk.types import SDKOperation, SDKOperationRequest
from aidbox_python_sdk_tbs import SubscriptionDefinition
from aidbox_python_sdk_tbs.r4b impotr r4b_tbs_ctx_factory
from aiohttp import web

from app import app_keys as ak
from app import config
from app.sdk import sdk

async def new_appointment_sub(app: web.Application, appointment: r4b.Appointment) -> None:
    fhir_client = app[ak.fhir_client]

    logging.error("New appointment %s", appointment.model_dump())


subscriptions: list[SubscriptionDefinition] = [
    {
        "topic": "https://example.com/SubscriptionTopic/new-appointment-event",
        "handler": new_appointment_sub,
        "filterBy": [
            {"resourceType": "Appointment", "filterParameter": "status", "value": "booked"}
        ],
    },
]


def aidbox_tbs_ctx(app: web.Application) -> AsyncGenerator[None, None]:
    return r4b_tbs_ctx_factory(
        app[ak.sdk],
        app[ak.settings].APP_INIT_URL,
        app[ak.fhir_client],
        subscriptions,
    )
```

New we need to build `app` composing different contexts. 
Pay attention, that app_ctx should be the last one, because `aidbox-python-sdk-tbs` adds endpoints to sdk.

Change `main.py` to look like the following example:

```python
from collections.abc import AsyncGenerator

from aidbox_python_sdk.main import init_client, register_app, setup_routes
from aidbox_python_sdk.settings import Settings
from aiohttp import BasicAuth, web
from fhirpy import AsyncFHIRClient

from app import app_keys as ak
from app.sdk import sdk
from app.subscriptions import aidbox_tbs_ctx


async def init_fhir_client(settings: Settings, prefix: str = "") -> AsyncFHIRClient:
    basic_auth = BasicAuth(
        login=settings.APP_INIT_CLIENT_ID,
        password=settings.APP_INIT_CLIENT_SECRET,
    )

    return AsyncFHIRClient(
        f"{settings.APP_INIT_URL}{prefix}",
        authorization=basic_auth.encode(),
        dump_resource=lambda x: x.model_dump(),
    )


async def fhir_client_ctx(app: web.Application) -> AsyncGenerator[None, None]:
    app[ak.fhir_client] = await init_fhir_client(app[ak.settings], "/fhir")
    yield


async def aidbox_client_ctx(app: web.Application) -> AsyncGenerator[None, None]:
    app[ak.client] = await init_client(app[ak.settings])
    yield


async def app_ctx(app: web.Application) -> AsyncGenerator[None, None]:
    await register_app(app[ak.sdk], app[ak.client])
    yield


def create_app() -> web.Application:
    app = web.Application()
    app[ak.sdk] = sdk
    app[ak.settings] = sdk.settings
    app.cleanup_ctx.append(aidbox_client_ctx)
    app.cleanup_ctx.append(fhir_client_ctx)
    app.cleanup_ctx.append(aidbox_tbs_ctx)
    # NOTE: Pay attention, app_ctx should be after aidbox_tbs_ctx !!!
    app.cleanup_ctx.append(app_ctx)

    setup_routes(app)

    return app


async def create_gunicorn_app() -> web.Application:
    return create_app()
```


