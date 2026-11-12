import { readdir, readFile } from "node:fs/promises";
import { gzipSync } from "node:zlib";

// Additive regression budgets, not an override of Vite's 500 KB warning.
// MapLibre remains a large lazy dependency; do not inflate that warning limit.
const assets = new URL("../dist/assets/", import.meta.url);
const groups = [
  { name: "entry JavaScript", pattern: /^index-.*\.js$/, max: 110_000 },
  { name: "lazy map JavaScript", pattern: /^WeatherMap-.*\.js$/, max: 320_000 },
  { name: "map worker", pattern: /^maplibre-gl-worker-.*\.mjs$/, max: 170_000 },
];
const files = await readdir(assets);
for (const group of groups) {
  const matches = files.filter((file) => group.pattern.test(file));
  if (matches.length !== 1) throw new Error(`Missing/ambiguous ${group.name}`);
  const bytes = gzipSync(
    await readFile(new URL(matches[0], assets)),
  ).byteLength;
  console.log(`Bundle budget: ${group.name}: ${bytes}/${group.max} gzip bytes`);
  if (bytes > group.max)
    throw new Error(`${group.name} exceeds its gzip budget`);
}
