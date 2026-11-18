import { memo, useId, useMemo, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { RainNextHourResponse } from "@wetmap/shared";
import {
  dryWindowDurations,
  findDryWindow,
  type DryWindowDuration,
} from "../dryWindow";
import { translate } from "../i18n";

interface Props {
  data?: RainNextHourResponse;
  now: number;
  isLoading: boolean;
  isError: boolean;
  locale: "da" | "en";
}

function windowTimes(
  startsAt: number,
  endsAt: number,
  now: number,
  locale: string,
) {
  const timeZone = "Europe/Copenhagen";
  const offset = new Intl.DateTimeFormat(locale, {
    timeZone,
    timeZoneName: "shortOffset",
  });
  const zoneAt = (value: number) =>
    offset.formatToParts(value).find((part) => part.type === "timeZoneName")
      ?.value;
  const endZone = zoneAt(endsAt);
  const showZone = zoneAt(now) !== endZone || zoneAt(startsAt) !== endZone;
  const formatter = new Intl.DateTimeFormat(locale, {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    ...(showZone ? { timeZoneName: "shortOffset" } : {}),
  });
  return { starts: formatter.format(startsAt), ends: formatter.format(endsAt) };
}

export default memo(function DryWindow({
  data,
  now,
  isLoading,
  isError,
  locale,
}: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [duration, setDuration] = useState<DryWindowDuration>(30);
  const t = (key: Parameters<typeof translate>[1]) => translate(locale, key);
  const intlLocale = locale === "da" ? "da-DK" : "en-GB";
  const result = open
    ? findDryWindow(isError ? undefined : data, now, duration)
    : null;
  let summary = "";
  let detail = "";
  if (result) {
    if (result.status === "found") {
      const { starts, ends } = windowTimes(
        result.startsAt,
        result.endsAt,
        now,
        intlLocale,
      );
      summary = t(result.startsAt === now ? "dryWindowNow" : "dryWindowLater")
        .replace("{start}", starts)
        .replace("{end}", ends);
      detail = t("dryWindowBasis");
    } else if (isLoading) {
      summary = t("dryWindowLoading");
    } else {
      summary = t("dryWindowNone");
      detail = t(
        result.status === "stale"
          ? "dryWindowStale"
          : result.status === "unavailable"
            ? "dryWindowUnavailable"
            : duration > 15
              ? "dryWindowTryShorter"
              : "dryWindowTryLater",
      );
    }
  }

  const durationFormatter = useMemo(
    () => new Intl.NumberFormat(intlLocale, { style: "unit", unit: "minute" }),
    [intlLocale],
  );
  return (
    <div className="dry-window">
      <button
        type="button"
        className="dry-window-toggle"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <span>{t(open ? "dryWindowHide" : "dryWindowOpen")}</span>
        {open ? (
          <ChevronUp size={16} aria-hidden="true" />
        ) : (
          <ChevronDown size={16} aria-hidden="true" />
        )}
      </button>
      <div id={id} className="dry-window-content" hidden={!open}>
        <fieldset className="dry-window-duration">
          <legend>{t("dryWindowDuration")}</legend>
          <div className="dry-window-options">
            {dryWindowDurations.map((value) => (
              <label key={value}>
                <input
                  type="radio"
                  name={id}
                  value={value}
                  checked={duration === value}
                  onChange={() => setDuration(value)}
                />
                {durationFormatter.format(value)}
              </label>
            ))}
          </div>
        </fieldset>
        <p className="dry-window-result" role="status" aria-atomic="true">
          {summary && <strong>{summary}</strong>}
          {detail && <span>{detail}</span>}
        </p>
      </div>
    </div>
  );
});
