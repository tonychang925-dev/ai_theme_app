import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./styles.css";

// P0-C1: StrictMode removed — prevents double-mount of useEffect in dev,
// which caused 2x SSE connections (4 instead of 2 for Kline+W2S alerts)
ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
