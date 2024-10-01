# fhir-tbs-py

Topic-based subscription extension for python aiohttp web applications

## Install

Install `fhir-tbs-py[r4b]` or `fhir-tbs-py[r5]` using poetry/pipenv/pip.

## Usage

Create `subscriptions.py` with the following content:

```python
import logging
from collections.abc import AsyncGenerator

from fhirpy import AsyncFHIRClient
import fhirpy_types_r4b as r4b
from fhir_tbs import SubscriptionDefinition
from fhir_tbs.r4b impotr r4b_tbs_ctx_factory
from aiohttp import web

# Make sure that app has fhir_client_key
fhir_client_key = web.AppKey("fhir_client_key", AsyncFHIRClient)


async def new_appointment_sub(app: web.Application, appointment_ref: str, _timestamp: str) -> None:
    fhir_client = app[fhir_client_key]
    appointment = r4b.Appointment(**(await fhir_client.get(appointment_ref)))
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


def tbs_ctx(app: web.Application) -> AsyncGenerator[None, None]:
    return r4b_tbs_ctx_factory(
        app,
        "http://app:8080",
        "webhook",
        app[fhir_client_key],
        subscriptions,
    )
```


Add `tbs_ctx` to `app.cleanup_ctx`.

