const DEVICE_ID_KEY = 'ibreeze_device_id';
const DEVICE_ID_COOKIE = 'ibreeze_device_id';

function parseCookies(): Record<string, string> {
  const cookies: Record<string, string> = {};
  document.cookie.split(';').forEach((c) => {
    const [key, ...rest] = c.split('=');
    if (key) cookies[key.trim()] = rest.join('=').trim();
  });
  return cookies;
}

function setCookie(name: string, value: string, days = 365): void {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)};expires=${expires};path=/;SameSite=Lax`;
}

export function getDeviceId(): string {
  const cookies = parseCookies();
  let deviceId = cookies[DEVICE_ID_COOKIE];

  if (!deviceId) {
    const stored = localStorage.getItem(DEVICE_ID_KEY);
    if (stored) deviceId = stored;
  }

  if (!deviceId) {
    deviceId = crypto.randomUUID();
  }

  localStorage.setItem(DEVICE_ID_KEY, deviceId);
  setCookie(DEVICE_ID_COOKIE, deviceId);

  return deviceId;
}
