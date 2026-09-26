"use client";

import { useEffect, useRef } from "react";
import maplibregl, { type Map as MapInstance, type Marker, type StyleSpecification } from "maplibre-gl";
import { demoDistrict, demoLayers, demoPlaces, type LayerId } from "@/lib/demo-data";
import type { LifePoint } from "@/lib/onboarding-store";

const style: StyleSpecification = { version: 8, sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } }, layers: [{ id: "osm", type: "raster", source: "osm" }] };
export default function DistrictMap({ active, points }: { active: LayerId[]; points: LifePoint[] }) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<MapInstance | null>(null);
  const markers = useRef<Marker[]>([]);
  useEffect(() => {
    if (!element.current) return;
    const instance = new maplibregl.Map({ container: element.current, style, center: demoDistrict.center, zoom: 12.2, minZoom: 9 });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.on("load", () => {
      instance.addSource("district-focus", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[92.96, 56.023], [93.092, 56.023], [93.102, 56.082], [92.961, 56.081], [92.96, 56.023]]] } } });
      instance.addLayer({ id: "district-fill", type: "fill", source: "district-focus", paint: { "fill-color": "#50c5a7", "fill-opacity": .08 } });
      instance.addLayer({ id: "district-outline", type: "line", source: "district-focus", paint: { "line-color": "#069b82", "line-width": 2, "line-dasharray": [2, 2] } });
    });
    map.current = instance;
    return () => { markers.current.forEach((marker) => marker.remove()); markers.current = []; instance.remove(); map.current = null; };
  }, []);
  useEffect(() => {
    if (!map.current) return;
    markers.current.forEach((marker) => marker.remove()); markers.current = [];
    const visible = demoPlaces.filter((place) => active.includes(place.layer));
    visible.forEach((place) => {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = "map-pin-demo";
      dot.setAttribute("aria-label", place.name);
      const layer = demoLayers.find((item) => item.id === place.layer);
      dot.style.backgroundColor = layer?.color ?? "#8be8d8";
      const popup = new maplibregl.Popup({ offset: 18 }).setText(place.name);
      markers.current.push(new maplibregl.Marker({ element: dot }).setLngLat(place.coordinates).setPopup(popup).addTo(map.current!));
    });
    if (active.includes("life")) points.forEach((point) => {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = "map-pin-life";
      dot.setAttribute("aria-label", point.name);
      markers.current.push(new maplibregl.Marker({ element: dot }).setLngLat([point.longitude, point.latitude]).setPopup(new maplibregl.Popup({ offset: 18 }).setText(point.name)).addTo(map.current!));
    });
  }, [active, points]);
  return <div ref={element} role="application" aria-label="Интерактивная карта демонстрационного района Красноярска" className="h-[460px] w-full overflow-hidden rounded-[24px] border border-[#cddfdb] sm:h-[580px] lg:h-[700px]" />;
}
