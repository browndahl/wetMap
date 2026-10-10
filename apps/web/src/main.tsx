import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { registerSW } from "virtual:pwa-register";
import App from "./App";
import DesignPage from "./DesignPage";
import "./styles.css";

registerSW({ immediate: true });

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 2, refetchOnWindowFocus: false } }
});

const Root = window.location.pathname === "/design" ? DesignPage : App;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Root />
    </QueryClientProvider>
  </StrictMode>
);
