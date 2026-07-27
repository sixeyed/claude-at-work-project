"""Pydantic DTOs and job payload models shared across CollabHub service boundaries.

Deliberately empty in the scaffold. The DTOs (`Message`, `Asset`, the job
envelope from Conventions §7, and the rest) arrive with the services that use
them, so that no model here exists without a producer and a consumer.

JSON is camelCase on the wire; models declare `alias_generator=to_camel` when
they land.
"""

__all__: list[str] = []
