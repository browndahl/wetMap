import { logEvent } from "./logging";

interface RadarSchedulerEnv {
  RADAR: R2Bucket;
  GITHUB_DISPATCH_TOKEN?: string;
  GITHUB_REPOSITORY?: string;
  GITHUB_RADAR_WORKFLOW?: string;
  GITHUB_REF?: string;
}

export const radarDispatchStateKey = "scheduler/radar-dispatch.json";
const minute = 60_000;
const publicationInterval = 6 * minute;
const inspectionCooldown = 2 * minute;
const dispatchCooldown = 5 * minute;

export interface RadarRecoveryState {
  checkedAt: string;
  lastDispatchedAt?: string;
  decision: "checking" | "active-run" | "dispatched" | "dispatch-failed";
  activeRunId?: number;
  dispatchError?: string;
}

interface WorkflowRun {
  id: number;
  status: string;
  created_at: string;
}

function recent(timestamp: string | undefined, interval: number): boolean {
  const age = Date.now() - Date.parse(timestamp ?? "");
  return Number.isFinite(age) && age >= -2 * minute && age < interval;
}

export async function ensureFreshRadar(env: RadarSchedulerEnv): Promise<void> {
  const object = await env.RADAR.get("frames/frames.json");
  if (object) {
    try {
      const manifest = await object.json<{
        generatedAt?: string;
        frames?: Array<{ observedAt?: string }>;
      }>();
      const observedAt = manifest.frames?.at(-1)?.observedAt;
      const validObservation =
        Number.isFinite(Date.parse(observedAt ?? "")) &&
        Date.parse(observedAt!) <= Date.now() + 2 * minute;
      // Publication is the ingestion heartbeat, not a replacement for observation
      // freshness. Recover BEFORE the 25-minute public freshness gate is crossed.
      // A freshly checked but delayed DMI source must not cause a dispatch storm.
      if (
        validObservation &&
        (manifest.generatedAt
          ? recent(manifest.generatedAt, publicationInterval)
          : recent(observedAt, 20 * minute))
      )
        return;
    } catch {
      logEvent("error", "radar.scheduler.invalid-manifest");
    }
  }
  if (!env.GITHUB_DISPATCH_TOKEN) {
    logEvent("error", "radar.scheduler.missing-token");
    return;
  }

  const stateObject = await env.RADAR.get(radarDispatchStateKey);
  const previous = stateObject
    ? await stateObject.json<Partial<RadarRecoveryState>>().catch(() => null)
    : null;
  if (
    recent(previous?.checkedAt, inspectionCooldown) ||
    recent(previous?.lastDispatchedAt, dispatchCooldown)
  )
    return;

  const next: RadarRecoveryState = {
    checkedAt: new Date().toISOString(),
    ...(previous?.lastDispatchedAt
      ? { lastDispatchedAt: previous.lastDispatchedAt }
      : {}),
    decision: "checking",
  };
  // Claim before external calls: concurrent cron isolates must not both dispatch.
  // A failed/ambiguous request retains a bounded cooldown, never an endless lock.
  const claimed = await env.RADAR.put(
    radarDispatchStateKey,
    JSON.stringify(next),
    {
      onlyIf: stateObject
        ? { etagMatches: stateObject.etag }
        : { etagDoesNotMatch: "*" },
      httpMetadata: { contentType: "application/json" },
    },
  );
  if (!claimed) return;

  const repository = env.GITHUB_REPOSITORY ?? "browndahl/wetMap";
  const workflow = env.GITHUB_RADAR_WORKFLOW ?? "radar.yml";
  const ref = env.GITHUB_REF ?? "main";
  const base = `https://api.github.com/repos/${repository}/actions/workflows/${workflow}`;
  const headers = {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
    "Content-Type": "application/json",
    "User-Agent": "wetmap-radar-scheduler/2.0",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  try {
    const url = new URL(`${base}/runs`);
    url.search = new URLSearchParams({
      branch: ref,
      per_page: "20",
    }).toString();
    const runsResponse = await fetch(url.toString(), {
      headers,
      signal: AbortSignal.timeout(10_000),
    });
    if (!runsResponse.ok) throw new Error("GitHub queue inspection failed");
    const payload = await runsResponse.json<{
      workflow_runs?: WorkflowRun[];
    }>();
    if (!Array.isArray(payload.workflow_runs))
      throw new Error("Invalid GitHub queue response");
    const active = payload.workflow_runs.find(
      (run) =>
        // created_at is NOT the actual runner start time. This is only a bounded
        // duplicate guard. Old queued/running records cannot block recovery forever.
        (run.status === "in_progress" && recent(run.created_at, 10 * minute)) ||
        (["queued", "pending", "waiting", "requested"].includes(run.status) &&
          recent(run.created_at, dispatchCooldown)),
    );
    if (active) {
      next.decision = "active-run";
      next.activeRunId = active.id;
    } else {
      const response = await fetch(`${base}/dispatches`, {
        method: "POST",
        headers,
        signal: AbortSignal.timeout(10_000),
        body: JSON.stringify({ ref }),
      });
      if (!response.ok) throw new Error("GitHub workflow dispatch failed");
      next.decision = "dispatched";
      next.lastDispatchedAt = new Date().toISOString();
      logEvent("info", "radar.scheduler.dispatched", {
        source: "github-actions",
      });
    }
  } catch {
    next.decision = "dispatch-failed";
    next.dispatchError = "github-inspection-or-dispatch-failed";
    logEvent("error", "radar.scheduler.dispatch-failed");
  }
  await env.RADAR.put(radarDispatchStateKey, JSON.stringify(next), {
    onlyIf: { etagMatches: claimed.etag },
    httpMetadata: { contentType: "application/json" },
  });
  if (next.dispatchError) throw new Error(next.dispatchError);
}
