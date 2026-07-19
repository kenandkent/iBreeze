import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Header } from './Header';
import { useAppStore } from '../../stores/appStore';
import type { PageKey } from '../../types';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}));

const PAGE_TITLE_MAP: Record<string, string> = {
  companies: '公司管理',
  employees: '员工管理',
  tasks: '任务看板',
  knowledge: '知识库',
  capabilities: '能力管理',
  skills: '技能管理',
  prompts: 'Prompt 资产',
  templates: '员工模板',
  settings: '设置',
};

describe('Header', () => {
  for (const [page, title] of Object.entries(PAGE_TITLE_MAP)) {
    it(`shows correct title for "${page}" → "${title}"`, () => {
      useAppStore.setState({ currentPage: page as PageKey });
      render(<Header />);
      expect(screen.getByText(title)).toBeInTheDocument();
    });
  }

  it('shows refresh button when onRefresh is provided', () => {
    const onRefresh = vi.fn();
    render(<Header onRefresh={onRefresh} />);
    expect(screen.getByText('刷新')).toBeInTheDocument();
  });

  it('hides refresh button when no onRefresh', () => {
    render(<Header />);
    expect(screen.queryByText('刷新')).not.toBeInTheDocument();
  });

  it('calls onRefresh on click', () => {
    const onRefresh = vi.fn();
    render(<Header onRefresh={onRefresh} />);
    fireEvent.click(screen.getByText('刷新'));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('falls back to iBreeze for unknown page', () => {
    useAppStore.setState({ currentPage: 'companies' as never });
    render(<Header />);
    expect(screen.getByText('公司管理')).toBeInTheDocument();
  });
});
