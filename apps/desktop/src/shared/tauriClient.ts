import { createRpcRequest } from "./rpcClient";

export interface ValidateOriginResult {
  valid: boolean;
  canonical_origin: string;
  app_user_id: string;
}

export interface RegisterResult {
  app_user_id: string;
  email: string;
  masked_identifier: string;
}

export interface LoginResult {
  status: "password_change_required" | "profile_opened";
  profile_directory_id: string;
  masked_identifier: string;
  catalog_release_sequence: number;
}

export interface LogoutResult {
  closed_profile: boolean;
  revoked_family: boolean;
}

export interface OfflineProfile {
  profile_directory_id: string;
  backend_origin: string;
  masked_identifier: string;
  expires_at: string;
}

export interface ListOfflineProfilesResult {
  profiles: OfflineProfile[];
}

export interface OpenProfileResult {
  profile_directory_id: string;
  mode: "online" | "offline";
  catalog_release_sequence: number;
}

export interface CloseProfileResult {
  closed_profile: boolean;
}

export async function validateOrigin(
  origin: string,
): Promise<ValidateOriginResult> {
  return createRpcRequest<ValidateOriginResult>("backend.validateOrigin", { origin });
}

export async function register(input: {
  email: string;
  password: string;
}): Promise<RegisterResult> {
  return createRpcRequest<RegisterResult>("auth.register", input);
}

export async function login(input: {
  email: string;
  password: string;
}): Promise<LoginResult> {
  return createRpcRequest<LoginResult>("auth.login", input);
}

export async function changePassword(input: {
  currentPassword: string;
  newPassword: string;
}): Promise<LoginResult> {
  return createRpcRequest<LoginResult>("auth.changePassword", {
    current_password: input.currentPassword,
    new_password: input.newPassword,
  });
}

export async function logout(): Promise<LogoutResult> {
  return createRpcRequest<LogoutResult>("auth.logout");
}

export async function listOfflineProfiles(): Promise<ListOfflineProfilesResult> {
  return createRpcRequest<ListOfflineProfilesResult>("auth.listOfflineProfiles");
}

export async function openProfile(
  profileDirectoryId: string,
): Promise<OpenProfileResult> {
  return createRpcRequest<OpenProfileResult>("auth.openProfile", {
    profile_directory_id: profileDirectoryId,
  });
}

export async function closeProfile(): Promise<CloseProfileResult> {
  return createRpcRequest<CloseProfileResult>("auth.closeProfile");
}
