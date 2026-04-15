import { useState } from "react";
import { stockScreenerApi } from "../../../lib/api/stockScreener";

interface ResultItem {
  result_id: string;
}

interface ExportPanelProps {
  results: ResultItem[];
  isOpen: boolean;
  onClose: () => void;
}

export function ExportPanel({ results, isOpen, onClose }: ExportPanelProps) {
  const [format, setFormat] = useState<"csv" | "excel" | "json">("json");
  const [message, setMessage] = useState<string>("");

  if (!isOpen) return null;

  const handleExport = async () => {
    try {
      const ids = results.map((x) => x.result_id);
      const res = await stockScreenerApi.exportResults(ids, format);
      setMessage(`导出成功：${res.data.download_url}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "导出失败";
      setMessage(msg);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-4 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-lg font-semibold">导出结果</h3>
          <button type="button" onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700">
            关闭
          </button>
        </div>
        <div className="space-y-3">
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value as "csv" | "excel" | "json")}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="json">JSON</option>
            <option value="csv">CSV</option>
            <option value="excel">Excel(导出为JSON)</option>
          </select>
          <button type="button" onClick={handleExport} className="w-full rounded bg-blue-600 px-3 py-2 text-sm text-white">
            立即导出
          </button>
          {message ? <p className="text-xs text-gray-600">{message}</p> : null}
        </div>
      </div>
    </div>
  );
}
