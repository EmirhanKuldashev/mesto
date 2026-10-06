"""Canonical component registry; computation remains entirely in each component."""
from importlib import import_module

COMPONENTS = {
    "stop_availability": "Stop", "school": "School", "kindergarten": "Kindergarten",
    "healthcare": "Healthcare", "parks": "Parks",
}


def contracts():
    for name, title in COMPONENTS.items():
        module = import_module(f"app.analytics.{name}.district")
        reference = import_module(f"app.analytics.{name}.reference")
        models = import_module(f"app.analytics.{name}.models")
        yield name, getattr(module, f"District{title}Availability"), getattr(
            module, f"District{title}AvailabilityService"), reference, models
