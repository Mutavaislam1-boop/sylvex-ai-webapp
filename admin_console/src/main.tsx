import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { setupTelegram } from "./telegram";
import "./styles.css";

setupTelegram();
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
