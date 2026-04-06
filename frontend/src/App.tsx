import { useEffect, useState } from "react";
import { IntelPage } from "./routes/intel/IntelPage";
import { RecapPage } from "./routes/recap/RecapPage";
import { StockWorkspacePage } from "./routes/stock/StockWorkspacePage";
import { ThemeWorkspacePage } from "./routes/theme/ThemeWorkspacePage";

export function App() {
  const [path, setPath] = useState(window.location.pathname);

  useEffect(() => {
    const handler = () => setPath(window.location.pathname);
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);

  if (path.startsWith("/themes/")) {
    const subjectKey = path.replace("/themes/", "").trim();
    return <ThemeWorkspacePage subjectKey={subjectKey} />;
  }

  if (path.startsWith("/stocks/")) {
    const stockId = path.replace("/stocks/", "").trim();
    return <StockWorkspacePage stockId={stockId} />;
  }

  if (path.startsWith("/recap")) {
    return <RecapPage />;
  }

  return <IntelPage />;
}
