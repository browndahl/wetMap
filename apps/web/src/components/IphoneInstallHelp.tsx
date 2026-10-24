import { Share } from "lucide-react";
import { translate } from "../i18n";

export default function IphoneInstallHelp({
  locale,
  expanded = false,
  onExpandedChange,
}: {
  locale: "da" | "en";
  expanded?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
}) {
  const t = (key: Parameters<typeof translate>[1]) => translate(locale, key);
  return (
    <details
      className="iphone-install-help"
      open={expanded || undefined}
      onToggle={(event) => onExpandedChange?.(event.currentTarget.open)}
    >
      <summary>
        <Share size={16} aria-hidden="true" />
        {t("iphoneInstallTitle")}
      </summary>
      <p>{t("iphoneInstallReason")}</p>
      <ol>
        <li>{t("iphoneInstallShare")}</li>
        <li>{t("iphoneInstallAdd")}</li>
        <li>{t("iphoneInstallOpen")}</li>
      </ol>
      <p>{t("iphoneInstallVersion")}</p>
    </details>
  );
}
