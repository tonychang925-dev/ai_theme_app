interface ErrorAlertProps {
  message: string;
  onClose?: () => void;
}

export function ErrorAlert({ message, onClose }: ErrorAlertProps) {
  return (
    <div className="rounded-md border border-red-200 bg-red-50 p-4 text-red-700">
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm">{message}</p>
        {onClose ? (
          <button onClick={onClose} className="text-xs text-red-600 hover:text-red-800" type="button">
            关闭
          </button>
        ) : null}
      </div>
    </div>
  );
}
