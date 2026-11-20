import { preferences } from '@kit.ArkData';
import { common } from '@kit.AbilityKit';

const STORE_NAME = 'xueji_prefs';
let cached: preferences.Preferences | null = null;

async function storeOf(context: common.Context): Promise<preferences.Preferences> {
  if (cached) {
    return cached;
  }
  cached = await preferences.getPreferences(context, STORE_NAME);
  return cached;
}

export async function readString(context: common.Context, key: string, fallback: string): Promise<string> {
  const store = await storeOf(context);
  const value = await store.get(key, fallback);
  if (typeof value === 'string') {
    return value;
  }
  return fallback;
}

export async function writeString(context: common.Context, key: string, value: string): Promise<void> {
  const store = await storeOf(context);
  await store.put(key, value);
  await store.flush();
}

export async function clearSession(context: common.Context): Promise<void> {
  await writeString(context, 'token', '');
  await writeString(context, 'nickname', '');
  await writeString(context, 'goalId', '');
}
