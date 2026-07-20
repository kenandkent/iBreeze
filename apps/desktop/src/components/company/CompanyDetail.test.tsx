import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CompanyDetail } from './CompanyDetail';
import type { Company } from '../../types';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

const mockCompany: Company = {
  company_id: 'comp-001',
  name: '测试公司',
  status: 'active',
  version: 1,
  created_at: '2025-01-15',
};

describe('CompanyDetail', () => {
  it('renders company name', () => {
    render(<CompanyDetail company={mockCompany} />);
    expect(screen.getByText('测试公司')).toBeInTheDocument();
  });

  it('renders status badge', () => {
    render(<CompanyDetail company={mockCompany} />);
    expect(screen.getByText('active')).toBeInTheDocument();
  });

  it('renders company ID', () => {
    render(<CompanyDetail company={mockCompany} />);
    expect(screen.getByText('comp-001')).toBeInTheDocument();
  });

  it('renders created_at', () => {
    render(<CompanyDetail company={mockCompany} />);
    expect(screen.getByText('2025-01-15')).toBeInTheDocument();
  });

  it('renders section labels', () => {
    render(<CompanyDetail company={mockCompany} />);
    expect(screen.getByText('ID')).toBeInTheDocument();
    expect(screen.getByText('创建时间')).toBeInTheDocument();
  });
});
