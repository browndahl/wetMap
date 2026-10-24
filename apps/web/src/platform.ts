// Platform detection is only used for installation instructions. Actual push support
// is still determined by the browser APIs when the user opts in.
export const needsIphoneInstallation = () => {
  const appleMobile =
    /iPhone|iPad|iPod/.test(navigator.userAgent) ||
    (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
  const installed = Boolean(
    (navigator as Navigator & { standalone?: boolean }).standalone ||
      window.matchMedia?.("(display-mode: standalone)").matches,
  );
  return appleMobile && !installed;
};
