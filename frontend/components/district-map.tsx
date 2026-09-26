"use client";

import { useEffect, useRef } from "react";
import maplibregl, { type Map as MapInstance, type Marker, type StyleSpecification } from "maplibre-gl";
import type { LifePoint } from "@/lib/onboarding-store";
import { scoreColor, type ScoredDistrict } from "@/lib/complex-scoring";

const style: StyleSpecification = { version: 8, sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } }, layers: [{ id: "osm", type: "raster", source: "osm" }] };

type Props = {
  points: LifePoint[];
  districts: ScoredDistrict[];
  selectedDistrictId: number | null;
  onSelectDistrict: (id: number) => void;
};

export default function DistrictMap({ points, districts, selectedDistrictId, onSelectDistrict }: Props) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<MapInstance | null>(null);
  const markers = useRef<Marker[]>([]);
  const selectedRef = useRef<number | null | undefined>(undefined);
  const onSelectRef = useRef(onSelectDistrict);
  onSelectRef.current = onSelectDistrict;

  useEffect(() => {
    if (!element.current) return;
    const instance = new maplibregl.Map({ container: element.current, style, center: [92.8526, 56.0106], zoom: 10, minZoom: 8 });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.current = instance;
    return () => {
      markers.current.forEach((marker) => marker.remove());
      markers.current = [];
      instance.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const geojson = {
      type: "FeatureCollection" as const,
      features: districts.map((district) => ({
        type: "Feature" as const,
        properties: { id: district.id, name: district.name, color: scoreColor(district.value) },
        geometry: district.geometry,
      })),
    };
    const render = () => {
      const source = instance.getSource("administrative-districts") as maplibregl.GeoJSONSource | undefined;
      if (source) source.setData(geojson);
      else {
        instance.addSource("administrative-districts", { type: "geojson", data: geojson });
        instance.addLayer({ id: "district-fill", type: "fill", source: "administrative-districts",
          paint: { "fill-color": ["get", "color"], "fill-opacity": 0.5 } });
        instance.addLayer({ id: "district-border", type: "line", source: "administrative-districts",
          paint: { "line-color": "#25515d", "line-width": 1.5 } });
        instance.on("click", "district-fill", (event) => {
          const id = Number(event.features?.[0]?.properties?.id);
          if (Number.isFinite(id)) onSelectRef.current(id);
        });
        instance.on("mouseenter", "district-fill", () => { instance.getCanvas().style.cursor = "pointer"; });
        instance.on("mouseleave", "district-fill", () => { instance.getCanvas().style.cursor = ""; });
      }
      instance.setPaintProperty("district-fill", "fill-opacity", selectedDistrictId === null ? 0.5 :
        ["case", ["==", ["get", "id"], selectedDistrictId], 0.38, 0.08]);
      instance.setPaintProperty("district-border", "line-width", selectedDistrictId === null ? 1.5 :
        ["case", ["==", ["get", "id"], selectedDistrictId], 3, 1]);

      if (districts.length && selectedRef.current !== selectedDistrictId) {
        const displayed = selectedDistrictId === null ? districts : districts.filter((district) => district.id === selectedDistrictId);
        const bounds = new maplibregl.LngLatBounds();
        for (const district of displayed) {
          for (const polygon of district.geometry.coordinates) {
            for (const ring of polygon) {
              for (const point of ring) bounds.extend([point[0], point[1]]);
            }
          }
        }
        if (!bounds.isEmpty()) instance.fitBounds(bounds, { padding: 45, maxZoom: selectedDistrictId === null ? 11 : 13, duration: 500 });
        selectedRef.current = selectedDistrictId;
      }

      markers.current.forEach((marker) => marker.remove());
      markers.current = [];
      if (selectedDistrictId === null) {
        districts.forEach((district) => {
          if (!district.centroid) return;
          const label = document.createElement("button");
          label.type = "button";
          label.className = "rounded-full border border-[#bdcfca] bg-white px-3 py-1.5 text-xs font-bold text-[#14333e] shadow-lg";
          label.textContent = `${district.name} · ${district.value === null ? "нет оценки" : district.value.toFixed(2)}`;
          label.setAttribute("aria-label", `Выбрать ${district.name} район`);
          label.onclick = () => onSelectRef.current(district.id);
          markers.current.push(new maplibregl.Marker({ element: label }).setLngLat(district.centroid.coordinates).addTo(instance));
        });
        return;
      }

      const selected = districts.find((district) => district.id === selectedDistrictId);
      selected?.complexes.filter((complex) => complex.location).forEach((complex) => {
        const dot = document.createElement("button");
        dot.type = "button";
        dot.className = "h-5 w-5 rounded-full border-2 border-white shadow-lg";
        dot.style.backgroundColor = scoreColor(complex.score.value);
        dot.setAttribute("aria-label", `${complex.name}: ${complex.score.value === null ? "нет оценки" : Math.round(complex.score.value * 100) + "%"}`);
        const content = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = complex.name;
        content.append(title);
        const score = document.createElement("p");
        score.textContent = complex.score.value === null ? "Недостаточно данных для оценки" :
          `Соответствие: ${Math.round(complex.score.value * 100)}% · покрытие: ${Math.round(complex.score.coverage * 100)}%`;
        content.append(score);
        if (complex.url && /^https:\/\/zhk-[a-z0-9-]+\.cian\.ru\/$/.test(complex.url)) {
          const link = document.createElement("a");
          link.href = complex.url;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = "Открыть на ЦИАН";
          content.append(link);
        }
        markers.current.push(new maplibregl.Marker({ element: dot })
          .setLngLat(complex.location!.coordinates)
          .setPopup(new maplibregl.Popup({ offset: 15 }).setDOMContent(content)).addTo(instance));
      });
      points.forEach((point) => {
        const dot = document.createElement("button");
        dot.type = "button";
        dot.className = "map-pin-life";
        dot.setAttribute("aria-label", point.name);
        markers.current.push(new maplibregl.Marker({ element: dot }).setLngLat([point.longitude, point.latitude])
          .setPopup(new maplibregl.Popup({ offset: 18 }).setText(point.name)).addTo(instance));
      });
    };
    if (instance.getSource("administrative-districts") || instance.isStyleLoaded()) render();
    else instance.once("load", render);
    return () => { instance.off("load", render); };
  }, [points, districts, selectedDistrictId]);

  return <div ref={element} role="application" aria-label="Карта административных районов и оценок ЖК" className="h-[460px] w-full overflow-hidden rounded-[24px] border border-[#cddfdb] sm:h-[580px] lg:h-[700px]" />;
}
