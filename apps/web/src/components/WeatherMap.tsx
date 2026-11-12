import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import type {
  GeoJSONSource,
  ImageSource,
  Map as MapLibreMap,
  MapMouseEvent,
  MapSourceDataEvent,
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
  onFrameReady?: (id: string) => void;
}

const framesBase =
  import.meta.env.VITE_FRAMES_BASE_URL || window.location.origin;

function markReady(name: string) {
  if (
    typeof performance.mark === "function" &&
    !performance.getEntriesByName(name).length
  )
    performance.mark(name);
}

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

export default function WeatherMap({
  frames,
  activeIndex,
  onFrameReady,
}: Props) {
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
  const frame = frames[activeIndex];

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
      markReady("wetmap:map-ready");
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
    const map = mapRef.current;
    if (!map || !frame) return;

    let cancelContent: (() => void) | undefined;
    let rendered = false;
    const renderWhenReady = () => {
      if (map.isStyleLoaded()) renderFrame();
    };
    const renderFrame = () => {
      if (rendered) return;
      rendered = true;
      map.off("load", renderFrame);
      map.off("style.load", renderFrame);
      map.off("styledata", renderWhenReady);
      const next = visibleBuffer.current === 0 ? 1 : 0;
      const sourceId = `radar-${next}`;
      const layerId = `radar-layer-${next}`;
      const oldLayerId = `radar-layer-${visibleBuffer.current}`;
      const absoluteUrl = new URL(frame.url, framesBase).toString();
      let visible = false;
      const showLoadedFrame = (event: MapSourceDataEvent) => {
        if (
          visible ||
          event.sourceId !== sourceId ||
          event.sourceDataType !== "content" ||
          !map.getLayer(layerId)
        )
          return;
        visible = true;
        map.off("sourcedata", showLoadedFrame);
        map.setPaintProperty(layerId, "raster-opacity", opacityRef.current);
        if (map.getLayer(oldLayerId))
          map.setPaintProperty(oldLayerId, "raster-opacity", 0);
        visibleBuffer.current = next;
        markReady("wetmap:radar-ready");
        onFrameReady?.(frame.id);
      };
      map.on("sourcedata", showLoadedFrame);
      cancelContent = () => map.off("sourcedata", showLoadedFrame);
      const existing = map.getSource(sourceId) as ImageSource | undefined;
      if (existing) {
        existing.updateImage({
          url: absoluteUrl,
          coordinates: imageCoordinates(frame),
        });
        return;
      }
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
          paint: {
            "raster-opacity": 0,
            "raster-fade-duration": 0,
            "raster-opacity-transition": {
              duration: window.matchMedia("(prefers-reduced-motion: reduce)")
                .matches
                ? 0
                : 120,
            },
          },
        },
        map.getLayer("wetmap-3d-buildings") ? "wetmap-3d-buildings" : undefined,
      );
    };

    if (map.isStyleLoaded()) renderFrame();
    else {
      // style.load/load prove the style can be edited. Do not recheck
      // isStyleLoaded inside their callback: another load handler may have just
      // added a GeoJSON source, making it temporarily false and losing this frame.
      map.on("load", renderFrame);
      map.on("style.load", renderFrame);
      map.on("styledata", renderWhenReady);
    }

    return () => {
      map.off("load", renderFrame);
      map.off("style.load", renderFrame);
      map.off("styledata", renderWhenReady);
      cancelContent?.();
    };
  }, [frame, onFrameReady]);

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
      if (map.getLayer(id))
        map.setPaintProperty(
          id,
          "raster-opacity",
          id === `radar-layer-${visibleBuffer.current}` ? opacity : 0,
        );
  }, [opacity]);

  return (
    <div
      ref={container}
      className="map"
      aria-label={`${translate(locale, "interactiveRadarMap")} ${selectedLocation.name}`}
    />
  );
}
