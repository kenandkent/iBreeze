import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EmployeeDetail } from './EmployeeDetail';
import type { Employee } from '../../types';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

const mockEmployee: Employee = {
  employee_id: 'emp-001',
  company_id: 'comp-001',
  department_id: 'dept-001',
  template_id: 'tpl-001',
  name: '张三',
  role_name: '工程师',
  employee_type: 'full-time',
  status: 'active',
};

describe('EmployeeDetail', () => {
  it('renders employee name', () => {
    render(<EmployeeDetail employee={mockEmployee} />);
    expect(screen.getByText('张三')).toBeInTheDocument();
  });

  it('renders status badge', () => {
    render(<EmployeeDetail employee={mockEmployee} />);
    expect(screen.getByText('active')).toBeInTheDocument();
  });

  it('renders role name', () => {
    render(<EmployeeDetail employee={mockEmployee} />);
    expect(screen.getByText('工程师')).toBeInTheDocument();
  });

  it('renders employee type', () => {
    render(<EmployeeDetail employee={mockEmployee} />);
    expect(screen.getByText('full-time')).toBeInTheDocument();
  });

  it('renders employee ID', () => {
    render(<EmployeeDetail employee={mockEmployee} />);
    expect(screen.getByText('emp-001')).toBeInTheDocument();
  });

  it('renders company ID', () => {
    render(<EmployeeDetail employee={mockEmployee} />);
    expect(screen.getByText('comp-001')).toBeInTheDocument();
  });

  it('renders section labels', () => {
    render(<EmployeeDetail employee={mockEmployee} />);
    expect(screen.getByText('角色')).toBeInTheDocument();
    expect(screen.getByText('类型')).toBeInTheDocument();
    expect(screen.getByText('ID')).toBeInTheDocument();
    expect(screen.getByText('所属公司')).toBeInTheDocument();
  });
});
