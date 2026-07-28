import { useAuthStore } from '../stores/authStore';

export interface QueryCtx {
  backendOrigin: string;
  appUserId: string;
  profileId: string;
}

export function useQueryCtx(): QueryCtx {
  const { backendOrigin, appUserId, profileDirectoryId } = useAuthStore();
  return {
    backendOrigin: backendOrigin ?? '',
    appUserId: appUserId ?? '',
    profileId: profileDirectoryId ?? '',
  };
}

export const queryKeys = {
  all: (ctx: QueryCtx) => [ctx.backendOrigin, ctx.appUserId, ctx.profileId] as const,

  company: (ctx: QueryCtx, companyId: string) =>
    [...queryKeys.all(ctx), 'companies', companyId] as const,
  companyList: (ctx: QueryCtx) =>
    [...queryKeys.all(ctx), 'companies'] as const,

  department: (ctx: QueryCtx, companyId: string, departmentId: string) =>
    [...queryKeys.all(ctx), companyId, 'departments', departmentId] as const,
  departmentList: (ctx: QueryCtx, companyId: string) =>
    [...queryKeys.all(ctx), companyId, 'departments'] as const,

  employee: (ctx: QueryCtx, companyId: string, departmentId: string | undefined) =>
    [...queryKeys.all(ctx), companyId, 'employees', departmentId] as const,
  employeeList: (ctx: QueryCtx, companyId: string) =>
    [...queryKeys.all(ctx), companyId, 'employees'] as const,

  task: (ctx: QueryCtx, companyId: string, taskId: string) =>
    [...queryKeys.all(ctx), companyId, 'tasks', taskId] as const,
  taskList: (ctx: QueryCtx, companyId: string, status?: string) =>
    [...queryKeys.all(ctx), companyId, 'tasks', status].filter(Boolean) as readonly string[],

  conversation: (ctx: QueryCtx, companyId: string, conversationId: string) =>
    [...queryKeys.all(ctx), companyId, 'conversations', conversationId] as const,
  conversationList: (ctx: QueryCtx, companyId: string) =>
    [...queryKeys.all(ctx), companyId, 'conversations'] as const,

  messageList: (ctx: QueryCtx, companyId: string, conversationId: string) =>
    [...queryKeys.all(ctx), companyId, 'conversations', conversationId, 'messages'] as const,

  workspace: (ctx: QueryCtx, companyId: string, workspaceId: string) =>
    [...queryKeys.all(ctx), companyId, 'workspaces', workspaceId] as const,
  workspaceList: (ctx: QueryCtx, companyId: string) =>
    [...queryKeys.all(ctx), companyId, 'workspaces'] as const,

  knowledge: (ctx: QueryCtx, companyId: string) =>
    [...queryKeys.all(ctx), companyId, 'knowledge'] as const,
  knowledgeSearch: (ctx: QueryCtx, companyId: string, query: string) =>
    [...queryKeys.all(ctx), companyId, 'knowledge', 'search', query] as const,

  auditLogList: (ctx: QueryCtx) =>
    [...queryKeys.all(ctx), 'auditLogs'] as const,

  reviewIssueList: (ctx: QueryCtx, companyId: string, artifactId: string) =>
    [...queryKeys.all(ctx), companyId, 'reviewIssues', artifactId] as const,
};
