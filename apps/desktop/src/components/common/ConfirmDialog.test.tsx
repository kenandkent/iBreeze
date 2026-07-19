import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ConfirmDialog } from './ConfirmDialog';

describe('ConfirmDialog', () => {
  const defaultProps = {
    open: true,
    title: '确认操作',
    message: '确定要执行此操作吗？',
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders when open', () => {
    render(<ConfirmDialog {...defaultProps} />);
    expect(screen.getByText('确认操作')).toBeInTheDocument();
    expect(screen.getByText('确定要执行此操作吗？')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    render(<ConfirmDialog {...defaultProps} open={false} />);
    expect(screen.queryByText('确认操作')).not.toBeInTheDocument();
  });

  it('calls onConfirm when confirm button clicked', () => {
    render(<ConfirmDialog {...defaultProps} />);
    screen.getByText('确认').click();
    expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when cancel button clicked', () => {
    render(<ConfirmDialog {...defaultProps} />);
    screen.getByText('取消').click();
    expect(defaultProps.onCancel).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when backdrop clicked', () => {
    render(<ConfirmDialog {...defaultProps} />);
    const backdrop = document.querySelector('.fixed') as HTMLElement;
    backdrop?.click();
    expect(defaultProps.onCancel).toHaveBeenCalled();
  });

  it('uses custom confirm label', () => {
    render(<ConfirmDialog {...defaultProps} confirmLabel="删除" />);
    expect(screen.getByText('删除')).toBeInTheDocument();
  });

  it('shows danger style by default', () => {
    render(<ConfirmDialog {...defaultProps} />);
    const confirmBtn = screen.getByText('确认');
    expect(confirmBtn.className).toContain('bg-red-600');
  });

  it('shows non-danger style when danger=false', () => {
    render(<ConfirmDialog {...defaultProps} danger={false} />);
    const confirmBtn = screen.getByText('确认');
    expect(confirmBtn.className).toContain('bg-blue-600');
  });
});
