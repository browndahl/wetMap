import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CheckCircle2,
  CloudRain,
  FlaskConical,
  MapPinned,
  ShieldAlert,
  X,
} from "lucide-react";
import type { PrecisionStatus, ShadowCandidateStatus } from "@wetmap/shared";
import { getPrecisionObservatory } from "../api";
import { translate } from "../i18n";

interface Props {
  locale: "da" | "en";
}

const formatTime = (value: string, locale: "da" | "en") =>
  new Intl.DateTimeFormat(locale === "da" ? "da-DK" : "en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Copenhagen",
  }).format(new Date(value));

const percentage = (value: number | null) =>
  value === null ? "–" : `${Math.round(value * 100)}%`;

const statusMessageKey = (status: PrecisionStatus) =>
  status === "verified"
    ? ("precisionVerified" as const)
    : status === "awaiting-rain"
      ? ("precisionAwaitingRain" as const)
      : status === "degraded"
        ? ("precisionDegraded" as const)
        : ("precisionCollecting" as const);

const shadowStatusMessageKey = (status: ShadowCandidateStatus) =>
  status === "promotable"
    ? ("precisionShadowPromotable" as const)
    : status === "held-back"
      ? ("precisionShadowHeldBack" as const)
      : status === "awaiting-rain"
        ? ("precisionShadowAwaitingRain" as const)
        : ("precisionShadowCollecting" as const);

export default function PrecisionObservatory({ locale }: Props) {
  const [open, setOpen] = useState(false);
  const t = (key: Parameters<typeof translate>[1]) => translate(locale, key);
  const quality = useQuery({
    queryKey: ["nowcast-quality"],
    queryFn: ({ signal }) => getPrecisionObservatory(signal),
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
    refetchIntervalInBackground: true,
    retry: 2,
  });
  const observatory = quality.data?.observatory;
  const groundGauge = quality.data?.groundGauge;
  const calibration = groundGauge?.calibration;
  const geographicConsistency = quality.data?.geographicConsistency;
  const shadowCandidate = quality.data?.shadowCandidates?.find(
    (candidate) => candidate.candidateId === "trajectory-recency-flow-v1",
  );
  const groundGaugeEvents = groundGauge
    ? groundGauge.hits + groundGauge.misses
    : 0;
  const groundGaugeMissRate =
    groundGauge && groundGaugeEvents > 0
      ? groundGauge.misses / groundGaugeEvents
      : null;
  const status: PrecisionStatus = observatory?.overallStatus ?? "collecting";
  const StatusIcon =
    status === "verified"
      ? CheckCircle2
      : status === "degraded"
        ? ShieldAlert
        : Activity;
  const statusClass = quality.isError ? "is-degraded" : `is-${status}`;

  return (
    <>
      <button
        type="button"
        className={`quality-trigger glass ${statusClass}`}
        aria-label={t("precisionOpen")}
        aria-expanded={open}
        aria-controls="precision-observatory"
        onClick={() => setOpen((value) => !value)}
      >
        <StatusIcon size={15} aria-hidden="true" />
        <span>{t("precisionShort")}</span>
        <i aria-hidden="true" />
      </button>

      {open && (
        <aside
          id="precision-observatory"
          className="quality-panel glass"
          aria-labelledby="precision-title"
        >
          <header className="quality-header">
            <div>
              <span className="eyebrow">
                <Activity size={14} aria-hidden="true" /> {t("precisionLive")}
              </span>
              <h2 id="precision-title">Precision Observatory</h2>
            </div>
            <button
              type="button"
              aria-label={t("precisionClose")}
              onClick={() => setOpen(false)}
            >
              <X size={17} aria-hidden="true" />
            </button>
          </header>

          {quality.isLoading && (
            <p className="quality-message" role="status">
              {t("precisionLoading")}
            </p>
          )}
          {quality.isError && (
            <p className="quality-message is-error">
              {t("precisionUnavailable")}
            </p>
          )}

          {quality.data && (
            <>
              <div className={`quality-overview ${statusClass}`}>
                <StatusIcon size={18} aria-hidden="true" />
                <div>
                  <strong>{t(statusMessageKey(status))}</strong>
                  <span>
                    {quality.data.sampleCount} {t("precisionVerifications")} ·{" "}
                    {observatory?.verifiedHorizonCount ?? 0}/4{" "}
                    {t("precisionHorizonsVerified")}
                  </span>
                </div>
              </div>

              <p className="quality-explanation">
                {t(
                  status === "awaiting-rain"
                    ? "precisionAwaitingRainDetail"
                    : status === "collecting"
                      ? "precisionCollectingDetail"
                      : status === "degraded"
                        ? "precisionDegradedDetail"
                        : "precisionVerifiedDetail",
                )}
              </p>

              <div className="quality-horizons">
                {(observatory?.horizons ?? []).map((horizon) => (
                  <article
                    className={`quality-horizon is-${horizon.status}`}
                    key={horizon.targetLeadMinutes}
                  >
                    <header>
                      <strong>+{horizon.targetLeadMinutes} min</strong>
                      <span>
                        +{horizon.windowStartMinutes}–{horizon.windowEndMinutes}
                      </span>
                    </header>
                    <dl>
                      <div>
                        <dt>{t("precisionCsi")}</dt>
                        <dd>{percentage(horizon.criticalSuccessIndex)}</dd>
                      </div>
                      <div>
                        <dt>{t("precisionFalseAlarms")}</dt>
                        <dd>{percentage(horizon.falseAlarmRate)}</dd>
                      </div>
                      <div>
                        <dt>{t("precisionMisses")}</dt>
                        <dd>{percentage(horizon.missRate)}</dd>
                      </div>
                    </dl>
                    <p>
                      {horizon.sampleCount} {t("precisionSamples")} ·{" "}
                      {horizon.eventPixelCount.toLocaleString(
                        locale === "da" ? "da-DK" : "en-GB",
                      )}{" "}
                      {t("precisionRainPixels")}
                    </p>
                    <em>{t(statusMessageKey(horizon.status))}</em>
                  </article>
                ))}
              </div>

              {!observatory && (
                <p className="quality-message">{t("precisionWarmingUp")}</p>
              )}

              {geographicConsistency && (
                <section
                  className={`quality-consistency is-${geographicConsistency.status}`}
                >
                  <MapPinned size={15} aria-hidden="true" />
                  <div>
                    <header>
                      <strong>{t("precisionGeographicConsistency")}</strong>
                      <span>
                        {t(
                          geographicConsistency.status === "verified"
                            ? "precisionConsistencyVerified"
                            : "precisionConsistencyDegraded",
                        )}
                      </span>
                    </header>
                    <p>
                      {geographicConsistency.locationCount}{" "}
                      {t("precisionLocations")} ·{" "}
                      {geographicConsistency.frameCount} {t("precisionFrames")}{" "}
                      ·{" "}
                      {geographicConsistency.comparisonCount.toLocaleString(
                        locale === "da" ? "da-DK" : "en-GB",
                      )}{" "}
                      {t("precisionMapPointComparisons")}
                    </p>
                    <small>
                      {geographicConsistency.rainClassificationMismatchCount}{" "}
                      {t("precisionRainMismatches")} ·{" "}
                      {geographicConsistency.valueMismatchCount}{" "}
                      {t("precisionValueMismatches")}
                    </small>
                  </div>
                </section>
              )}

              {shadowCandidate && (
                <section className="quality-shadow">
                  <header>
                    <span>
                      <FlaskConical size={15} aria-hidden="true" />
                      <strong>{t("precisionShadowTitle")}</strong>
                    </span>
                    <em>{t("precisionShadowLive")}</em>
                  </header>
                  <p>{t("precisionShadowDetail")}</p>
                  <div>
                    {shadowCandidate.byLeadMinutes.map((lead) => (
                      <article
                        className={`is-${lead.status}`}
                        key={lead.leadMinutes}
                      >
                        <header>
                          <strong>+{lead.leadMinutes} min</strong>
                          <span>{t(shadowStatusMessageKey(lead.status))}</span>
                        </header>
                        <dl>
                          <div>
                            <dt>{t("precisionImprovement")}</dt>
                            <dd>
                              {lead.criticalSuccessIndexImprovement === null
                                ? "–"
                                : `${lead.criticalSuccessIndexImprovement >= 0 ? "+" : ""}${Math.round(lead.criticalSuccessIndexImprovement * 100)} pp`}
                            </dd>
                          </div>
                          <div>
                            <dt>{t("precisionFalseAlarmChange")}</dt>
                            <dd>
                              {lead.falseAlarmRateIncrease === null
                                ? "–"
                                : `${lead.falseAlarmRateIncrease >= 0 ? "+" : ""}${Math.round(lead.falseAlarmRateIncrease * 100)} pp`}
                            </dd>
                          </div>
                        </dl>
                        <small>
                          {lead.sampleCount}/
                          {shadowCandidate.promotionGate.minimumSamples}{" "}
                          {t("precisionSamples")}
                        </small>
                      </article>
                    ))}
                  </div>
                  <small>{t("precisionShadowSafety")}</small>
                </section>
              )}

              <div className="quality-ground">
                <CloudRain size={15} aria-hidden="true" />
                <div>
                  <strong>{t("precisionGroundCheck")}</strong>
                  <span>
                    {groundGauge
                      ? `${groundGauge.stationComparisonCount.toLocaleString(
                          locale === "da" ? "da-DK" : "en-GB",
                        )} ${t("precisionStationComparisons")}`
                      : t("precisionGroundPending")}
                  </span>
                  {groundGauge && (
                    <>
                      <dl>
                        <div>
                          <dt>{t("precisionGaugeDetected")}</dt>
                          <dd>{percentage(groundGauge.recall)}</dd>
                        </div>
                        <div>
                          <dt>{t("precisionGaugeMissed")}</dt>
                          <dd>{percentage(groundGaugeMissRate)}</dd>
                        </div>
                      </dl>
                      <small>
                        {calibration?.appliedThresholdDbz ??
                          quality.data.thresholdDbz}{" "}
                        dBZ {t("precisionGaugeThreshold")}
                      </small>
                    </>
                  )}
                </div>
              </div>

              {calibration && (
                <section className="quality-calibration">
                  <header>
                    <strong>{t("precisionCalibration")}</strong>
                    <span>
                      {t(
                        calibration.status === "calibrated"
                          ? "precisionCalibrationCalibrated"
                          : calibration.status === "inconclusive"
                            ? "precisionCalibrationInconclusive"
                            : calibration.status === "awaiting-overlap"
                              ? "precisionCalibrationAwaiting"
                              : "precisionCalibrationCollecting",
                      )}
                    </span>
                  </header>
                  <p>
                    {t("precisionAppliedThreshold")}:{" "}
                    <strong>{calibration.appliedThresholdDbz} dBZ</strong> ·{" "}
                    {t("precisionRadius")}{" "}
                    <strong>{calibration.appliedSpatialRadiusPixels} px</strong>
                  </p>
                  <div className="quality-thresholds">
                    {calibration.candidates
                      .filter(
                        (candidate) =>
                          candidate.spatialRadiusPixels ===
                          calibration.appliedSpatialRadiusPixels,
                      )
                      .map((candidate) => (
                        <div
                          className={candidate.eligible ? "is-eligible" : ""}
                          key={candidate.thresholdDbz}
                        >
                          <strong>{candidate.thresholdDbz} dBZ</strong>
                          <span>
                            CSI {percentage(candidate.criticalSuccessIndex)} ·{" "}
                            {t("precisionGaugeDetectedShort")}{" "}
                            {percentage(candidate.recall)}
                          </span>
                        </div>
                      ))}
                  </div>
                  <small>
                    {calibration.observationCount}/
                    {calibration.minimumObservationCount}{" "}
                    {t("precisionCalibrationRuns")} ·{" "}
                    {t("precisionCalibrationSafety")}
                  </small>
                  {calibration.safeToPromote &&
                    calibration.forecastQualityStatus !== "verified" && (
                      <small className="is-warning">
                        {t("precisionCalibrationForecastGate")}
                      </small>
                    )}
                </section>
              )}

              <footer className="quality-footer">
                <span>
                  {t("precisionUpdated")}{" "}
                  {formatTime(quality.data.generatedAt, locale)}
                </span>
                <span>
                  {calibration?.appliedThresholdDbz ??
                    quality.data.thresholdDbz}{" "}
                  dBZ · {quality.data.algorithmVersion}
                </span>
              </footer>
            </>
          )}
        </aside>
      )}
    </>
  );
}
