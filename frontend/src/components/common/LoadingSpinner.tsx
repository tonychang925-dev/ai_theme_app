interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function LoadingSpinner({ size = 'md', className = '' }: LoadingSpinnerProps) {
  const sizeClass = size === 'sm' ? 'h-4 w-4' : size === 'lg' ? 'h-8 w-8' : 'h-6 w-6';
  const classes = 'inline-block ' + sizeClass + ' animate-spin rounded-full border-2 border-gray-300 border-t-blue-600 ' + className;
  return <span className={classes} aria-label="loading" />;
}
