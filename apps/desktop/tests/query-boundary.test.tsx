import { describe, it, expect } from 'vitest';
import { queryKeys } from '../src/shared/queryKeys';
import type { QueryCtx } from '../src/shared/queryKeys';

const ctxA: QueryCtx = {
  backendOrigin: 'https://server-a.example.com',
  appUserId: 'user-1',
  profileId: 'profile-1',
};

const ctxB: QueryCtx = {
  backendOrigin: 'https://server-b.example.com',
  appUserId: 'user-2',
  profileId: 'profile-2',
};

const ctxASame: QueryCtx = {
  backendOrigin: 'https://server-a.example.com',
  appUserId: 'user-1',
  profileId: 'profile-1',
};

describe('query key isolation', () => {
  it('different origins produce different keys', () => {
    const keyA = queryKeys.companyList(ctxA);
    const keyB = queryKeys.companyList(ctxB);
    expect(keyA).not.toEqual(keyB);
  });

  it('different app users produce different keys', () => {
    const ctxDiffUser: QueryCtx = { ...ctxA, appUserId: 'user-3' };
    const keyA = queryKeys.companyList(ctxA);
    const keyB = queryKeys.companyList(ctxDiffUser);
    expect(keyA).not.toEqual(keyB);
  });

  it('different profiles produce different keys', () => {
    const ctxDiffProfile: QueryCtx = { ...ctxA, profileId: 'profile-3' };
    const keyA = queryKeys.companyList(ctxA);
    const keyB = queryKeys.companyList(ctxDiffProfile);
    expect(keyA).not.toEqual(keyB);
  });

  it('same context produces equal keys', () => {
    const keyA = queryKeys.companyList(ctxA);
    const keyB = queryKeys.companyList(ctxASame);
    expect(keyA).toEqual(keyB);
  });

  it('different company IDs isolate company detail keys', () => {
    const keyA = queryKeys.company(ctxA, 'company-1');
    const keyB = queryKeys.company(ctxA, 'company-2');
    expect(keyA).not.toEqual(keyB);
  });

  it('different entity types isolate keys at same context', () => {
    const companyKey = queryKeys.companyList(ctxA);
    const deptKey = queryKeys.departmentList(ctxA, 'c-1');
    expect(companyKey).not.toEqual(deptKey);
  });

  it('all factory starts with [backendOrigin, appUserId, profileId]', () => {
    const keys = [
      queryKeys.companyList(ctxA),
      queryKeys.departmentList(ctxA, 'c-1'),
      queryKeys.employeeList(ctxA, 'c-1'),
      queryKeys.taskList(ctxA, 'c-1'),
      queryKeys.conversationList(ctxA, 'c-1'),
      queryKeys.workspaceList(ctxA, 'c-1'),
      queryKeys.knowledge(ctxA, 'c-1'),
      queryKeys.auditLogList(ctxA),
      queryKeys.orchestrationList(ctxA),
    ];
    for (const key of keys) {
      expect(key[0]).toBe(ctxA.backendOrigin);
      expect(key[1]).toBe(ctxA.appUserId);
      expect(key[2]).toBe(ctxA.profileId);
    }
  });
});
