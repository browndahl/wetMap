import { lazy, Suspense } from "react";
import App from "./App";

const DesignPage = lazy(() => import("./DesignPage"));

export default function Root() {
  return window.location.pathname === "/design" ? (
    <Suspense fallback={null}>
      <DesignPage />
    </Suspense>
  ) : (
    <App />
  );
}
