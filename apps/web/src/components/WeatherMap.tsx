import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import type {
  GeoJSONSource,
  Map as MapLibreMap,
  MapMouseEvent,
} from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import type { NowcastFrame, RadarFrame } from "@wetmap/shared";
import { useWeatherStore } from "../store";
import { translate } from "../i18n";
import "maplibre-gl/dist/maplibre-gl.css";

// MapLibre's ESM build resolves its worker relative to the final JavaScript
// chunk. Make Vite emit the worker explicitly so production servers do not
// fall back to index.html for that request.
maplibregl.setWorkerUrl(maplibreWorkerUrl);

interface Props {
  frames: Array<RadarFrame | NowcastFrame>;
  activeIndex: number;
}

const framesBase =
  import.meta.env.VITE_FRAMES_BASE_URL || window.location.origin;

const imageCoordinates = (
  frame: RadarFrame | NowcastFrame,
): [[number, number], [number, number], [number, number], [number, number]] => {
  const [west, south, east, north] = frame.bounds;
  return [
    [west, north],
    [east, north],
    [east, south],
    [west, south],
  ];
};

function addBuildings(map: MapLibreMap) {
  if (map.getLayer("wetmap-3d-buildings")) return;
  const labelLayer = map
    .getStyle()
    .layers.find(
      (layer) =>
        layer.type === "symbol" &&
        "layout" in layer &&
        layer.layout?.["text-field"],
    );
  map.addLayer(
    {
      id: "wetmap-3d-buildings",
      source: "openmaptiles",
      "source-layer": "building",
      type: "fill-extrusion",
      minzoom: 14,
      paint: {
        "fill-extrusion-color": [
          "interpolate",
          ["linear"],
          ["get", "render_height"],
          0,
          "#172638",
          60,
          "#375066",
        ],
        "fill-extrusion-height": [
          "coalesce",
          ["get", "render_height"],
          ["get", "height"],
          8,
        ],
        "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
        "fill-extrusion-opacity": 0.86,
      },
    },
    labelLayer?.id,
  );
}

export default function WeatherMap({ frames, activeIndex }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const visibleBuffer = useRef<0 | 1>(0);
  const opacityRef = useRef(0.7);
  const opacity = useWeatherStore((state) => state.opacity);
  const precise2d = useWeatherStore((state) => state.precise2d);
  const locale = useWeatherStore((state) => state.locale);
  const selectedLocation = useWeatherStore((state) => state.selectedLocation);
  const setSelectedLocation = useWeatherStore(
    (state) => state.setSelectedLocation,
  );

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const initial = useWeatherStore.getState();
    const map = new maplibregl.Map({
      container: container.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [
        initial.selectedLocation.longitude,
        initial.selectedLocation.latitude,
      ],
      zoom: 14.5,
      pitch: initial.precise2d ? 0 : 55,
      bearing: 0,
      attributionControl: false,
      canvasContextAttributes: { antialias: !initial.precise2d },
    });
    map.addControl(
      new maplibregl.NavigationControl({ visualizePitch: true }),
      "top-right",
    );
    map.addControl(
      new maplibregl.GeolocateControl({
        positionOptions: { enableHighAccuracy: true },
        trackUserLocation: true,
      }),
      "top-right",
    );
    map.on("load", () => {
      if (!useWeatherStore.getState().precise2d) addBuildings(map);
      const location = useWeatherStore.getState().selectedLocation;
      map.addSource("selected-location", {
        type: "geojson",
        data: {
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [location.longitude, location.latitude],
          },
          properties: {},
        },
      });
      map.addLayer({
        id: "selected-location",
        source: "selected-location",
        type: "circle",
        paint: {
          "circle-radius": 7,
          "circle-color": "#76eaf2",
          "circle-stroke-color": "#07111f",
          "circle-stroke-width": 3,
        },
      });
    });
    map.on("click", (event: MapMouseEvent) => {
      const point = {
        id: `map:${event.lngLat.lat.toFixed(5)},${event.lngLat.lng.toFixed(5)}`,
        name: `${event.lngLat.lat.toFixed(3)}°N, ${event.lngLat.lng.toFixed(3)}°E`,
        context: translate(useWeatherStore.getState().locale, "selectedOnMap"),
        latitude: event.lngLat.lat,
        longitude: event.lngLat.lng,
      };
      setSelectedLocation(point);
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [setSelectedLocation]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const updateLocation = () => {
      (
        map.getSource("selected-location") as GeoJSONSource | undefined
      )?.setData({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [selectedLocation.longitude, selectedLocation.latitude],
        },
        properties: {},
      });
      map.easeTo({
        center: [selectedLocation.longitude, selectedLocation.latitude],
        zoom: 14.5,
        duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? 0
          : 650,
      });
    };
    if (map.isStyleLoaded()) updateLocation();
    else map.once("load", updateLocation);
    return () => {
      map.off("load", updateLocation);
    };
  }, [selectedLocation]);

  useEffect(() => {
    const preloaded = frames
      .slice(activeIndex, activeIndex + (precise2d ? 2 : 3))
      .map((frame) => {
        const image = new Image();
        image.crossOrigin = "anonymous";
        image.decoding = "async";
        image.src = new URL(frame.url, framesBase).toString();
        return image;
      });
    return () =>
      preloaded.forEach((image) => {
        image.onload = null;
        image.onerror = null;
      });
  }, [activeIndex, frames, precise2d]);

  useEffect(() => {
    const map = mapRef.current;
    const frame = frames[activeIndex];
    if (!map || !frame) return;

    let fadeTimer: number | undefined;
    let rendered = false;
    const renderFrame = () => {
      if (rendered || !map.isStyleLoaded()) return;
      rendered = true;
      map.off("load", renderFrame);
      map.off("styledata", renderFrame);
      const next = visibleBuffer.current === 0 ? 1 : 0;
      const sourceId = `radar-${next}`;
      const layerId = `radar-layer-${next}`;
      const oldLayerId = `radar-layer-${visibleBuffer.current}`;
      const absoluteUrl = new URL(frame.url, framesBase).toString();
      if (map.getLayer(layerId)) map.removeLayer(layerId);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
      map.addSource(sourceId, {
        type: "image",
        url: absoluteUrl,
        coordinates: imageCoordinates(frame),
      });
      map.addLayer(
        {
          id: layerId,
          type: "raster",
          source: sourceId,
          paint: { "raster-opacity": 0, "raster-fade-duration": 280 },
        },
        map.getLayer("wetmap-3d-buildings") ? "wetmap-3d-buildings" : undefined,
      );
      fadeTimer = window.setTimeout(() => {
        if (!map.getLayer(layerId)) return;
        map.setPaintProperty(layerId, "raster-opacity", opacityRef.current);
        if (map.getLayer(oldLayerId))
          map.setPaintProperty(oldLayerId, "raster-opacity", 0);
        visibleBuffer.current = next;
      }, 40);
    };

    if (map.isStyleLoaded()) renderFrame();
    else {
      // `isStyleLoaded()` can briefly be false after MapLibre's one-time load
      // event. Listening to styledata as well prevents the first radar frame
      // from waiting for a later playback change before it becomes visible.
      map.on("load", renderFrame);
      map.on("styledata", renderFrame);
    }

    return () => {
      map.off("load", renderFrame);
      map.off("styledata", renderFrame);
      if (fadeTimer !== undefined) window.clearTimeout(fadeTimer);
    };
  }, [activeIndex, frames]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const applyBuildings = () => {
      if (!precise2d) addBuildings(map);
      if (map.getLayer("wetmap-3d-buildings"))
        map.setLayoutProperty(
          "wetmap-3d-buildings",
          "visibility",
          precise2d ? "none" : "visible",
        );
    };
    map.easeTo({
      pitch: precise2d ? 0 : 55,
      duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? 0
        : 500,
    });
    if (map.isStyleLoaded()) applyBuildings();
    else map.on("load", applyBuildings);
    return () => {
      map.off("load", applyBuildings);
    };
  }, [precise2d]);

  useEffect(() => {
    const map = mapRef.current;
    opacityRef.current = opacity;
    if (!map) return;
    for (const id of ["radar-layer-0", "radar-layer-1"])
      if (map.getLayer(id)) map.setPaintProperty(id, "raster-opacity", opacity);
  }, [opacity]);

  return (
    <div
      ref={container}
      className="map"
      aria-label={`${translate(locale, "interactiveRadarMap")} ${selectedLocation.name}`}
    />
  );
}
