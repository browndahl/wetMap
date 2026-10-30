export interface OperationsEnv {
  RADAR: R2Bucket;
  OPERATIONS_MONITOR_ENABLED?: string;
  MONITOR_REPORT_TOKEN?: string;
  GITHUB_DISPATCH_TOKEN?: string;
  GITHUB_REPOSITORY?: string;
  GITHUB_REF?: string;
}

const probeKey = "monitoring/probe.json";
const schedulerKey = "monitoring/scheduler.json";
const minute = 60_000;
const checkNames = [
  "web",
  "api",
  "radar",
  "quality",
  "performance",
  "scheduler",
];
type Check = { name: string; ok: boolean; code: string; durationMs: number };
type Report = { runId: string; checkedAt: string; checks: Check[] };
type Incident = {
  id: string;
  signature: string;
  openedAt: string;
  updatedAt: string;
  resolvedAt?: string;
};
type Acknowledgement = {
  accepted: boolean;
  shouldFail: boolean;
  transition: string;
  incidentId: string | null;
};
type ProbeState = Report & {
  receivedAt: string;
  incident: Incident | null;
  lastIncident: Incident | null;
  acknowledgement: Acknowledgement;
};
type SchedulerState = {
  checkedAt: string;
  lastDispatchedAt?: string;
  dispatchError?: string;
};

const enabled = (env: OperationsEnv) =>
  env.OPERATIONS_MONITOR_ENABLED === "true" &&
  Boolean(env.MONITOR_REPORT_TOKEN);
const age = (timestamp?: string) =>
  timestamp ? (Date.now() - Date.parse(timestamp)) / minute : Infinity;
const recent = (timestamp: string | undefined, minutes: number) =>
  age(timestamp) >= -2 && age(timestamp) <= minutes;
const json = (body: unknown, status = 200) =>
  Response.json(body, { status, headers: { "Cache-Control": "no-store" } });
const condition = (object: R2ObjectBody | null) =>
  object ? { etagMatches: object.etag } : { etagDoesNotMatch: "*" };

async function read<T>(bucket: R2Bucket, key: string): Promise<T | null> {
  const object = await bucket.get(key);
  return object ? await object.json<T>() : null;
}

export function classifyRadar(
  manifest: {
    generatedAt?: string;
    frames?: Array<{ observedAt?: string }>;
  } | null,
) {
  const observedAt = manifest?.frames?.at(-1)?.observedAt;
  const observationAge = age(observedAt);
  const valid = Number.isFinite(observationAge) && observationAge >= -2;
  const ok = valid && observationAge <= 25;
  return {
    ok,
    code: ok
      ? "ok"
      : !valid
        ? "invalid-manifest"
        : recent(manifest?.generatedAt, 15)
          ? "source-delayed"
          : "ingestion-stalled",
    observedAt: observedAt ?? null,
    ageMinutes: valid ? Math.round(observationAge * 10) / 10 : null,
    lastPublicationAt: manifest?.generatedAt ?? null,
  };
}

export async function operationsStatus(env: OperationsEnv): Promise<Response> {
  try {
    const [probe, scheduler, manifest] = await Promise.all([
      read<ProbeState>(env.RADAR, probeKey),
      read<SchedulerState>(env.RADAR, schedulerKey),
      read<Parameters<typeof classifyRadar>[0]>(
        env.RADAR,
        "frames/frames.json",
      ),
    ]);
    const schedulerOk =
      recent(scheduler?.checkedAt, 10) && !scheduler?.dispatchError;
    const probeOk = recent(probe?.receivedAt, 35);
    const radar = classifyRadar(manifest);
    const monitoringActive = enabled(env) && schedulerOk && probeOk;
    const healthy =
      monitoringActive &&
      radar.ok &&
      Boolean(probe?.checks.every((check) => check.ok));
    return json(
      {
        schemaVersion: 1,
        generatedAt: new Date().toISOString(),
        status: healthy ? "healthy" : "degraded",
        monitoringEnabled: enabled(env),
        monitoringActive,
        scheduler: {
          ok: schedulerOk,
          checkedAt: scheduler?.checkedAt ?? null,
          lastDispatchedAt: scheduler?.lastDispatchedAt ?? null,
          dispatchError: scheduler?.dispatchError ?? null,
        },
        probe: {
          ok: probeOk,
          checkedAt: probe?.checkedAt ?? null,
          receivedAt: probe?.receivedAt ?? null,
          runId: probe?.runId ?? null,
        },
        radar,
        checks: probe?.checks ?? [],
        activeIncident: probe?.incident ?? null,
        lastIncident: probe?.lastIncident ?? null,
      },
      healthy ? 200 : 503,
    );
  } catch {
    return json(
      {
        schemaVersion: 1,
        status: "degraded",
        monitoringActive: false,
        code: "monitor-state-unavailable",
      },
      503,
    );
  }
}

function validReport(value: unknown): value is Report {
  if (!value || typeof value !== "object") return false;
  const data = value as Report;
  return (
    typeof data.runId === "string" &&
    /^\d{1,20}(?:-\d{1,3})?$/.test(data.runId) &&
    typeof data.checkedAt === "string" &&
    /(Z|\+00:00)$/.test(data.checkedAt) &&
    recent(data.checkedAt, 2) &&
    Array.isArray(data.checks) &&
    data.checks.length === checkNames.length &&
    new Set(data.checks.map((check) => check?.name)).size ===
      checkNames.length &&
    data.checks.every(
      (check) =>
        check &&
        typeof check === "object" &&
        checkNames.includes(check.name) &&
        typeof check.ok === "boolean" &&
        typeof check.code === "string" &&
        /^[a-z][a-z0-9-]{0,63}$/.test(check.code) &&
        (check.ok ? check.code === "ok" : check.code !== "ok") &&
        Number.isFinite(check.durationMs) &&
        check.durationMs >= 0 &&
        check.durationMs <= 300_000,
    )
  );
}

// This private mutation is deliberately separate from browser-origin mutations.
// A high-entropy bearer token is required; no personal or arbitrary payload is saved.
export async function receiveOperationsReport(
  request: Request,
  env: OperationsEnv,
): Promise<Response> {
  if (!enabled(env)) return json({ error: "monitoring-disabled" }, 503);
  if (
    request.headers.get("Authorization") !==
    `Bearer ${env.MONITOR_REPORT_TOKEN}`
  )
    return json({ error: "unauthorized" }, 401);
  if (Number(request.headers.get("Content-Length") || 0) > 16_384)
    return json({ error: "report-too-large" }, 413);
  let payload: unknown;
  try {
    // Bound chunked bodies too; Content-Length is not a security boundary.
    const reader = request.body?.getReader();
    if (!reader) return json({ error: "invalid-report" }, 400);
    const chunks: Uint8Array[] = [];
    let size = 0;
    for (;;) {
      const chunk = await reader.read();
      if (chunk.done) break;
      size += chunk.value.length;
      if (size > 16_384) {
        await reader.cancel();
        return json({ error: "report-too-large" }, 413);
      }
      chunks.push(chunk.value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.length;
    }
    payload = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return json({ error: "invalid-report" }, 400);
  }
  if (!validReport(payload)) return json({ error: "invalid-report" }, 400);
  const report: Report = {
    runId: payload.runId,
    checkedAt: payload.checkedAt,
    checks: payload.checks.map(({ name, ok, code, durationMs }) => ({
      name,
      ok,
      code,
      durationMs,
    })),
  };
  const signature = report.checks
    .filter((check) => !check.ok)
    .map((check) => `${check.name}:${check.code}`)
    .sort()
    .join(",");
  try {
    for (let attempt = 0; attempt < 4; attempt++) {
      const object = await env.RADAR.get(probeKey);
      const previous = object
        ? await object.json<ProbeState>().catch(() => null)
        : null;
      if (previous?.runId === report.runId)
        return json(previous.acknowledgement);
      if (
        previous &&
        Date.parse(previous.checkedAt) > Date.parse(report.checkedAt)
      )
        return json({
          accepted: false,
          shouldFail: false,
          transition: "superseded",
          incidentId: previous.incident?.id ?? null,
        });
      const timestamp = new Date().toISOString();
      const changed =
        Boolean(signature) && signature !== previous?.incident?.signature;
      const incident = !signature
        ? null
        : changed
          ? {
              id: crypto.randomUUID(),
              signature,
              openedAt: timestamp,
              updatedAt: timestamp,
            }
          : { ...previous!.incident!, updatedAt: timestamp };
      const lastIncident =
        !signature && previous?.incident
          ? { ...previous.incident, resolvedAt: timestamp }
          : (previous?.lastIncident ?? null);
      const acknowledgement: Acknowledgement = {
        accepted: true,
        shouldFail: changed,
        transition: changed
          ? "opened"
          : signature
            ? "ongoing"
            : previous?.incident
              ? "recovered"
              : "healthy",
        incidentId: incident?.id ?? lastIncident?.id ?? null,
      };
      const next: ProbeState = {
        ...report,
        receivedAt: timestamp,
        incident,
        lastIncident,
        acknowledgement,
      };
      const stored = await env.RADAR.put(probeKey, JSON.stringify(next), {
        onlyIf: condition(object),
        httpMetadata: { contentType: "application/json" },
      });
      if (stored) return json(acknowledgement);
    }
    return json({ error: "report-contention" }, 409);
  } catch {
    return json({ error: "report-storage-failed" }, 503);
  }
}

export async function scheduleOperations(env: OperationsEnv): Promise<void> {
  if (!enabled(env)) return;
  const [object, probe] = await Promise.all([
    env.RADAR.get(schedulerKey),
    read<ProbeState>(env.RADAR, probeKey),
  ]);
  const previous = object
    ? await object.json<SchedulerState>().catch(() => null)
    : null;
  const due =
    !recent(probe?.receivedAt, 15) &&
    !recent(previous?.lastDispatchedAt, 15 - 1 / 60_000);
  if (!due && recent(previous?.checkedAt, 5 - 1 / 60_000)) return;
  const timestamp = new Date().toISOString();
  const next: SchedulerState = {
    ...previous,
    checkedAt: timestamp,
    ...(due ? { lastDispatchedAt: timestamp, dispatchError: undefined } : {}),
  };
  // Claim the bounded dispatch slot before making an external call. Overlapping
  // isolates cannot both win the same ETag; a failed call retains the cooldown.
  const claimed = await env.RADAR.put(schedulerKey, JSON.stringify(next), {
    onlyIf: condition(object),
    httpMetadata: { contentType: "application/json" },
  });
  if (!claimed || !due) return;
  try {
    if (!env.GITHUB_DISPATCH_TOKEN) throw new Error("Missing dispatch token");
    const repository = env.GITHUB_REPOSITORY ?? "browndahl/wetMap";
    const response = await fetch(
      `https://api.github.com/repos/${repository}/actions/workflows/synthetic.yml/dispatches`,
      {
        method: "POST",
        signal: AbortSignal.timeout(10_000),
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
          "Content-Type": "application/json",
          "User-Agent": "wetmap-operations/1.0",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({ ref: env.GITHUB_REF ?? "main" }),
      },
    );
    if (!response.ok) throw new Error("Dispatch rejected");
  } catch {
    await env.RADAR.put(
      schedulerKey,
      JSON.stringify({ ...next, dispatchError: "github-dispatch-failed" }),
      {
        onlyIf: { etagMatches: claimed.etag },
        httpMetadata: { contentType: "application/json" },
      },
    );
    throw new Error("GitHub monitoring dispatch failed");
  }
}
