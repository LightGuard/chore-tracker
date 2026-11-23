import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "reshaped/themes/slate/theme.css";
import "./styles.css";
import "./admin/admin-themes.css";
import { App } from "./App";
import { applyInitialDocumentTheme } from "./theme/storage";

applyInitialDocumentTheme();

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error('The application root element "#root" was not found.');
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
