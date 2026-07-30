import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { queryKeys, useQueryCtx } from '../../src/shared/queryKeys';
import { useAuthStore } from '../../src/stores/authStore';

const ctx = {
  backendOrigin: 'https://test.com',
  appUserId: 'user-1',
  profileId: 'profile-1',
};

describe('queryKeys', () => {
  it('all returns base keys', () => {
    const keys = queryKeys.all(ctx);
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1']);
  });

  it('company returns correct keys', () => {
    const keys = queryKeys.company(ctx, 'c1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'companies', 'c1']);
  });

  it('companyList returns correct keys', () => {
    const keys = queryKeys.companyList(ctx);
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'companies']);
  });

  it('department returns correct keys', () => {
    const keys = queryKeys.department(ctx, 'c1', 'd1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'departments', 'd1']);
  });

  it('departmentList returns correct keys', () => {
    const keys = queryKeys.departmentList(ctx, 'c1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'departments']);
  });

  it('employee returns correct keys', () => {
    const keys = queryKeys.employee(ctx, 'c1', 'd1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'employees', 'd1']);
  });

  it('employee returns keys with undefined dept', () => {
    const keys = queryKeys.employee(ctx, 'c1', undefined);
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'employees', undefined]);
  });

  it('employeeList returns correct keys', () => {
    const keys = queryKeys.employeeList(ctx, 'c1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'employees']);
  });

  it('task returns correct keys', () => {
    const keys = queryKeys.task(ctx, 'c1', 't1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'tasks', 't1']);
  });

  it('taskList returns correct keys without status', () => {
    const keys = queryKeys.taskList(ctx, 'c1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'tasks']);
  });

  it('taskList returns correct keys with status', () => {
    const keys = queryKeys.taskList(ctx, 'c1', 'pending');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'tasks', 'pending']);
  });

  it('conversation returns correct keys', () => {
    const keys = queryKeys.conversation(ctx, 'c1', 'conv1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'conversations', 'conv1']);
  });

  it('conversationList returns correct keys', () => {
    const keys = queryKeys.conversationList(ctx, 'c1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'conversations']);
  });

  it('messageList returns correct keys', () => {
    const keys = queryKeys.messageList(ctx, 'c1', 'conv1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'conversations', 'conv1', 'messages']);
  });

  it('workspace returns correct keys', () => {
    const keys = queryKeys.workspace(ctx, 'c1', 'w1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'workspaces', 'w1']);
  });

  it('workspaceList returns correct keys', () => {
    const keys = queryKeys.workspaceList(ctx, 'c1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'workspaces']);
  });

  it('knowledge returns correct keys', () => {
    const keys = queryKeys.knowledge(ctx, 'c1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'knowledge']);
  });

  it('knowledgeSearch returns correct keys', () => {
    const keys = queryKeys.knowledgeSearch(ctx, 'c1', 'query');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'knowledge', 'search', 'query']);
  });

  it('auditLogList returns correct keys', () => {
    const keys = queryKeys.auditLogList(ctx);
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'auditLogs']);
  });

  it('reviewIssueList returns correct keys', () => {
    const keys = queryKeys.reviewIssueList(ctx, 'c1', 'a1');
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'c1', 'reviewIssues', 'a1']);
  });

  it('orchestrationList returns correct keys', () => {
    const keys = queryKeys.orchestrationList(ctx);
    expect(keys).toEqual(['https://test.com', 'user-1', 'profile-1', 'orchestrations']);
  });
});

function QueryCtxDisplay() {
  const ctx = useQueryCtx();
  return (
    <div>
      <span data-testid="backendOrigin">{ctx.backendOrigin}</span>
      <span data-testid="appUserId">{ctx.appUserId}</span>
      <span data-testid="profileId">{ctx.profileId}</span>
    </div>
  );
}

describe('useQueryCtx', () => {
  beforeEach(() => {
    useAuthStore.setState({
      backendOrigin: null,
      appUserId: null,
      profileDirectoryId: null,
    });
  });

  it('returns empty strings when store values are null', () => {
    render(<QueryCtxDisplay />);
    expect(screen.getByTestId('backendOrigin').textContent).toBe('');
    expect(screen.getByTestId('appUserId').textContent).toBe('');
    expect(screen.getByTestId('profileId').textContent).toBe('');
  });

  it('returns store values when set', () => {
    useAuthStore.setState({
      backendOrigin: 'https://example.com',
      appUserId: 'user-123',
      profileDirectoryId: 'profile-456',
    });
    render(<QueryCtxDisplay />);
    expect(screen.getByTestId('backendOrigin').textContent).toBe('https://example.com');
    expect(screen.getByTestId('appUserId').textContent).toBe('user-123');
    expect(screen.getByTestId('profileId').textContent).toBe('profile-456');
  });
});
