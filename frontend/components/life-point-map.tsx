"use client";

import { useEffect, useRef } from "react";
import maplibregl, { type Map as MapInstance, type Marker, type StyleSpecification } from "maplibre-gl";
import type { Coordinates } from "@/lib/onboarding-store";

const mapStyle: StyleSpecification = {
  version: 8,
  sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    tileSize: 256, attribution: "© OpenStreetMap contributors" } },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

export default function LifePointMap({ value, onChange }: { value: Coordinates | null; onChange: (point: Coordinates) => void }) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<MapInstance | null>(null);
  const marker = useRef<Marker | null>(null);
  const callback = useRef(onChange);
  const initial = useRef(value);

  useEffect(() => { callback.current = onChange; }, [onChange]);

  useEffect(() => {
    if (!element.current) return;
    const instance = new maplibregl.Map({ container: element.current, style: mapStyle,
      center: initial.current ? [initial.current.longitude, initial.current.latitude] : [92.87, 56.01], zoom: 11 });
    instance.addControl(new maplibregl.NavigationControl(), "top-right");
    instance.on("click", (event) => callback.current({ longitude: event.lngLat.lng, latitude: event.lngLat.lat }));
    map.current = instance;
    return () => { marker.current?.remove(); marker.current = null; instance.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    if (!map.current) return;
    if (!value) { marker.current?.remove(); marker.current = null; return; }
    if (!marker.current) {
      marker.current = new maplibregl.Marker({ color: "#0f766e", draggable: true })
        .setLngLat([value.longitude, value.latitude]).addTo(map.current);
      marker.current.on("dragend", () => {
        const position = marker.current?.getLngLat();
        if (position) callback.current({ longitude: position.lng, latitude: position.lat });
      });
    } else {
      marker.current.setLngLat([value.longitude, value.latitude]);
    }
  }, [value]);

  return <div ref={element} className="h-72 w-full overflow-hidden rounded-2xl border border-slate-200" role="application" aria-label="Карта выбора точки в Красноярске" />;
}
