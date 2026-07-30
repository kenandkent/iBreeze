import { type ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';

export function createTestQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
}

export function TestProviders({ children, qc }: { children: ReactElement; qc?: QueryClient }) {
  const client = qc ?? createTestQueryClient();
  return (
    <ConfigProvider locale={zhCN}>
      <QueryClientProvider client={client}>
        {children}
      </QueryClientProvider>
    </ConfigProvider>
  );
}
