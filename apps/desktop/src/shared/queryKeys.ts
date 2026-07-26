export const queryKeys = {
  company: (ctx: { backendOrigin: string; appUserId: string; profileId: string }, companyId: string) =>
    [ctx.backendOrigin, ctx.appUserId, ctx.profileId, companyId, "company"] as const,
  resource: (ctx: { backendOrigin: string; appUserId: string; profileId: string }, companyId: string, type: string, id: string) =>
    [ctx.backendOrigin, ctx.appUserId, ctx.profileId, companyId, type, id] as const,
};
