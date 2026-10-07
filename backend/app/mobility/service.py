from datetime import datetime
from typing import Protocol

from .models import Coordinate, Mode, MobilityRequest, MobilityResult, RouteFacts


class RoutingProvider(Protocol):
    def route(self, origin: Coordinate, destination: Coordinate, mode: Mode,
              departure_time: datetime | None = None) -> RouteFacts: ...


class PublicTransportRoutingProvider:
    """No licensed, verified Krasnoyarsk schedule source is configured in V1."""
    def route(self, origin, destination, mode, departure_time=None) -> RouteFacts:
        return RouteFacts(availability="UNAVAILABLE", unavailable_reason="public_transport_source_unavailable",
                          limitations=("No verified licensed schedule/routing source; OSM stops are not transit routes.",))


class MobilityService:
    def __init__(self, car: RoutingProvider, public_transport: RoutingProvider | None = None):
        self.providers = {"car": car, "public_transport": public_transport or PublicTransportRoutingProvider()}

    def calculate(self, request: MobilityRequest) -> MobilityResult:
        # Labels/kinds are UI metadata, never sent to the routing provider.
        destination = Coordinate(latitude=request.destination.latitude, longitude=request.destination.longitude)
        facts = self.providers[request.mode].route(request.origin, destination, request.mode, request.departure_time)
        return MobilityResult(**facts.model_dump(), mode=request.mode, origin=request.origin,
                              destination=request.destination, departure_time=request.departure_time,
                              traffic="not_included" if request.mode == "car" else "not_available")
