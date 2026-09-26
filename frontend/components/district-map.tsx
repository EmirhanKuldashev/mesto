"use client";

import { useEffect, useRef } from "react";
import maplibregl, { type Map as MapInstance, type Marker, type StyleSpecification } from "maplibre-gl";
import type { LifePoint } from "@/lib/onboarding-store";
import { scoreColor, type FutureObject, type Poi, type ScoredDistrict } from "@/lib/complex-scoring";

const style: StyleSpecification = { version: 8, sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } }, layers: [{ id: "osm", type: "raster", source: "osm" }] };

export type MapLayer = "housing" | "schools" | "kindergarten" | "healthcare" | "transport" | "parks" | "future";

function layerForPoi(category: string): MapLayer | null {
  if (category === "school") return "schools";
  if (category === "kindergarten") return "kindergarten";
  if (["hospital", "clinic"].includes(category)) return "healthcare";
  if (["bus_stop", "tram_stop", "transport_stop"].includes(category)) return "transport";
  if (category === "park") return "parks";
  return null;
}

function inRing(point: [number, number], ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j];
    if ((a[1] > point[1]) !== (b[1] > point[1]) &&
        point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
}

function inDistrict(point: [number, number], district: ScoredDistrict): boolean {
  return district.geometry.coordinates.some((polygon) => polygon.length > 0 &&
    inRing(point, polygon[0]) && !polygon.slice(1).some((hole) => inRing(point, hole)));
}

function distanceLabel(point: [number, number], district: ScoredDistrict): string | null {
  if (!district.centroid) return null;
  const center = district.centroid.coordinates;
  const latitude = (point[1] + center[1]) / 2 * Math.PI / 180;
  const meters = Math.round(Math.hypot((point[0] - center[0]) * Math.cos(latitude), point[1] - center[1]) * 111320);
  return `До центра района: ${meters < 1000 ? `${meters} м` : `${(meters / 1000).toFixed(1)} км`} по прямой`;
}

type Props = {
  points: LifePoint[];
  districts: ScoredDistrict[];
  pois: Poi[];
  futureObjects: FutureObject[];
  layers: Record<MapLayer, boolean>;
  selectedDistrictId: number | null;
  onSelectDistrict: (id: number) => void;
};

export default function DistrictMap({ points, districts, pois, futureObjects, layers, selectedDistrictId, onSelectDistrict }: Props) {
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
          label.textContent = `${district.name} · ${district.value === null ? "нет оценки" : `${Math.round(district.value * 100)}/100`}`;
          label.setAttribute("aria-label", `Выбрать ${district.name} район`);
          label.onclick = () => onSelectRef.current(district.id);
          markers.current.push(new maplibregl.Marker({ element: label }).setLngLat(district.centroid.coordinates).addTo(instance));
        });
        return;
      }

      const selected = districts.find((district) => district.id === selectedDistrictId);
      selected?.complexes.filter((complex) => layers.housing && complex.location).forEach((complex) => {
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
        const price = document.createElement("p");
        price.textContent = `Тип: жилой комплекс · Цена от: ${complex.price_from ? `${new Intl.NumberFormat("ru-RU").format(complex.price_from)} ₽` : "не указана"}`;
        content.append(price);
        const distance = selected ? distanceLabel(complex.location!.coordinates, selected) : null;
        if (distance) { const note = document.createElement("p"); note.textContent = distance; content.append(note); }
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
      if (selected) {
        pois.filter((poi) => {
          const layer = layerForPoi(poi.category);
          return layer && layers[layer] && inDistrict(poi.location.coordinates, selected);
        }).forEach((poi) => {
          const layer = layerForPoi(poi.category)!;
          const dot = document.createElement("button");
          dot.type = "button";
          dot.className = "h-4 w-4 rounded-full border-2 border-white shadow-lg";
          dot.style.backgroundColor = layer === "schools" || layer === "kindergarten" ? "#247fc1" :
            layer === "healthcare" ? "#e8757b" : layer === "transport" ? "#dc9f3b" : "#37a577";
          dot.setAttribute("aria-label", poi.name);
          const content = document.createElement("div");
          const title = document.createElement("strong"); title.textContent = poi.name;
          const type = document.createElement("p"); type.textContent = `Тип: ${poi.category}`;
          content.append(title, type);
          const distance = distanceLabel(poi.location.coordinates, selected);
          if (distance) { const note = document.createElement("p"); note.textContent = distance; content.append(note); }
          markers.current.push(new maplibregl.Marker({ element: dot }).setLngLat(poi.location.coordinates)
            .setPopup(new maplibregl.Popup({ offset: 15 }).setDOMContent(content)).addTo(instance));
        });
        if (layers.future) futureObjects.filter((item) => item.district_id === selected.id && item.location).forEach((item) => {
          const dot = document.createElement("button"); dot.type = "button";
          dot.className = "h-5 w-5 rounded-full border-2 border-white bg-[#8764b7] shadow-lg";
          dot.setAttribute("aria-label", item.name);
          const content = document.createElement("div");
          const title = document.createElement("strong"); title.textContent = item.name;
          const type = document.createElement("p"); type.textContent = `Будущий объект · ${item.category}`;
          const status = document.createElement("p");
          status.textContent = `Статус: ${item.status}${item.planned_year ? ` · ${item.planned_year}` : ""}${item.is_synthetic ? " · Демо-данные" : ""}`;
          content.append(title, type, status);
          const distance = distanceLabel(item.location!.coordinates, selected);
          if (distance) { const note = document.createElement("p"); note.textContent = distance; content.append(note); }
          markers.current.push(new maplibregl.Marker({ element: dot }).setLngLat(item.location!.coordinates)
            .setPopup(new maplibregl.Popup({ offset: 15 }).setDOMContent(content)).addTo(instance));
        });
      }
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
  }, [points, districts, pois, futureObjects, layers, selectedDistrictId]);

  return <div ref={element} role="application" aria-label="Карта административных районов и оценок ЖК" className="h-[460px] w-full overflow-hidden rounded-[24px] border border-[#cddfdb] sm:h-[580px] lg:h-[700px]" />;
}
