from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from .models import MobilityRequest, MobilityResult
from .osrm import CarRoutingProvider
from .service import MobilityService

class MobilityRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validate(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # Nonstandard JSON NaN/Infinity can reach the JSON decoder.
                # Never echo nonfinite input into JSONResponse (which rejects
                # it and would turn a coordinate validation error into a 500).
                return JSONResponse(status_code=422, content={"detail": [
                    {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ]})
        return validate


router = APIRouter(prefix="/api/analytics", tags=["mobility"], route_class=MobilityRoute)


def get_mobility_service() -> MobilityService:
    return MobilityService(CarRoutingProvider.from_environment())


@router.post("/mobility", response_model=MobilityResult)
def calculate_mobility(request: MobilityRequest, service: MobilityService = Depends(get_mobility_service)):
    return service.calculate(request)
