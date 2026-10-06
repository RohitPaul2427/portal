import React from "react";
import ReactDOM from "react-dom/client";
import axios from "axios";
import "@/index.css";
import App from "@/App";

// The API base URL should come from REACT_APP_BACKEND_URL at build time
// (e.g. REACT_APP_BACKEND_URL=https://api.leamss.com npm run build).
// Safety net: if a build was accidentally made with the localhost default and
// is served from a *.leamss.com domain, route API calls to the live API.
const LIVE_API = "https://api.leamss.com";
const API_ORIGIN = (() => {
  try { return new URL(process.env.REACT_APP_BACKEND_URL || "http://localhost:8001").origin; } catch { return ""; }
})();

axios.interceptors.request.use((config) => {
  const onLiveDomain = typeof window !== "undefined" && window.location.hostname.endsWith("leamss.com");
  if (onLiveDomain) {
    if (config.url && config.url.includes("localhost:8001")) {
      config.url = config.url.replace(/http:\/\/localhost:8001/g, LIVE_API);
    } else if (config.baseURL && config.baseURL.includes("localhost:8001")) {
      config.baseURL = config.baseURL.replace(/http:\/\/localhost:8001/g, LIVE_API);
    }
  }

  // Attach the staff login token to calls to OUR API when the caller forgot to.
  // Never send it to third-party hosts.
  try {
    const target = new URL(config.url, config.baseURL || window.location.href);
    const ours = target.origin === API_ORIGIN || target.origin === LIVE_API || target.origin === window.location.origin;
    const hasAuth = config.headers && (config.headers.Authorization || config.headers.authorization);
    const token = window.localStorage.getItem("token");
    if (ours && !hasAuth && token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch { /* ignore malformed URLs */ }
  return config;
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

