import { Loader2 } from 'lucide-react';

export function LoadingSpinner({ text = '加载中...' }: { text?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-8 text-gray-400">
      <Loader2 className="w-5 h-5 animate-spin" />
      <span className="text-sm">{text}</span>
    </div>
  );
}
