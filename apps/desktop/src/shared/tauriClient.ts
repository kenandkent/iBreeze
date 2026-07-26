import { invoke } from "@tauri-apps/api/core";

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
  return invoke<ValidateOriginResult>("backend_validateOrigin", { origin });
}

export async function register(input: {
  email: string;
  password: string;
}): Promise<RegisterResult> {
  return invoke<RegisterResult>("auth_register", input);
}

export async function login(input: {
  email: string;
  password: string;
}): Promise<LoginResult> {
  return invoke<LoginResult>("auth_login", input);
}

export async function changePassword(input: {
  current_password: string;
  new_password: string;
}): Promise<LoginResult> {
  return invoke<LoginResult>("auth_changePassword", input);
}

export async function logout(): Promise<LogoutResult> {
  return invoke<LogoutResult>("auth_logout");
}

export async function listOfflineProfiles(): Promise<ListOfflineProfilesResult> {
  return invoke<ListOfflineProfilesResult>("auth_listOfflineProfiles");
}

export async function openProfile(
  profileDirectoryId: string,
): Promise<OpenProfileResult> {
  return invoke<OpenProfileResult>("auth_openProfile", {
    profileDirectoryId,
  });
}

export async function closeProfile(): Promise<CloseProfileResult> {
  return invoke<CloseProfileResult>("auth_closeProfile");
}
