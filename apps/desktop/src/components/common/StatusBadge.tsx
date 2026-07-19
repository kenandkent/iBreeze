import clsx from 'clsx';

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  healthy: 'bg-green-100 text-green-800',
  inactive: 'bg-gray-100 text-gray-600',
  pending: 'bg-yellow-100 text-yellow-800',
  error: 'bg-red-100 text-red-800',
  unhealthy: 'bg-red-100 text-red-800',
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? 'bg-blue-100 text-blue-800';
  return (
    <span className={clsx('inline-block px-2 py-0.5 rounded-full text-xs font-medium', style)}>
      {status}
    </span>
  );
}
