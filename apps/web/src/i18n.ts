const messages = {
  da: {
    radar: "Radar",
    observed: "Observeret",
    noData: "Venter på radardata",
    noDataDetail: "Kør workeren for at hente de seneste DMI-observationer.",
    play: "Afspil radar",
    pause: "Sæt radar på pause",
    opacity: "Radar-gennemsigtighed",
    precise: "2D præcision",
    forecast: "Punktprognose",
    now: "Nu",
    fresh: "Opdateret",
    stale: "Data er forsinkede",
    locate: "Find min placering",
    language: "Skift sprog",
    buildings: "3D-bygninger",
    reflectivity: "Reflektivitet · dBZ"
  },
  en: {
    radar: "Radar",
    observed: "Observed",
    noData: "Waiting for radar data",
    noDataDetail: "Run the worker to fetch the latest DMI observations.",
    play: "Play radar",
    pause: "Pause radar",
    opacity: "Radar opacity",
    precise: "2D precision",
    forecast: "Point forecast",
    now: "Now",
    fresh: "Updated",
    stale: "Data is delayed",
    locate: "Find my location",
    language: "Change language",
    buildings: "3D buildings",
    reflectivity: "Reflectivity · dBZ"
  }
} as const;

export type MessageKey = keyof (typeof messages)["da"];
export const translate = (locale: keyof typeof messages, key: MessageKey) => messages[locale][key];
