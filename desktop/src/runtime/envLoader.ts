import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { app } from 'electron';

export interface EnvConfig {
  JWT_SECRET: string;
  DATABASE_URL: string;
  REDIS_URL: string;
  DEEPSEEK_API_KEY: string;
  TUSHARE_TOKEN: string;
  WEB_APP_READ_MODE: string;
  STOCK_PROCESSING_READ_BASE_URL: string;
  HF_HUB_OFFLINE: string;
  FRONTEND_DIST_DIR: string;
  MOBILE_ACCESS_TOKEN: string;
}

function userConfigDir(): string {
  return path.join(app.getPath('userData'), 'config');
}

function userEnvLocalPath(): string {
  return path.join(userConfigDir(), '.env.local');
}

function generateJwtSecret(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-';
  let result = '';
  for (let i = 0; i < 64; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

function parseEnvFile(filePath: string): Record<string, string> {
  const result: Record<string, string> = {};
  if (!fs.existsSync(filePath)) return result;
  const content = fs.readFileSync(filePath, 'utf-8');
  for (const raw of content.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const eqIdx = line.indexOf('=');
    const key = line.substring(0, eqIdx).trim();
    let value = line.substring(eqIdx + 1).trim();
    // Strip surrounding quotes
    if ((value.startsWith("'") && value.endsWith("'")) ||
        (value.startsWith('"') && value.endsWith('"'))) {
      value = value.slice(1, -1);
    }
    if (key && value) {
      result[key] = value;
    }
  }
  return result;
}

export function loadEnv(projectRoot: string): Record<string, string> {
  const merged: Record<string, string> = {};

  // Layer 1: project .env.theme and .env (lowest priority)
  const projectEnvFiles = [
    path.join(projectRoot, '.env.theme'),
    path.join(projectRoot, '.env'),
  ];
  for (const file of projectEnvFiles) {
    Object.assign(merged, parseEnvFile(file));
  }

  // Layer 2: user config .env.local (higher priority)
  const userConfig = userConfigDir();
  if (!fs.existsSync(userConfig)) {
    fs.mkdirSync(userConfig, { recursive: true });
  }
  Object.assign(merged, parseEnvFile(userEnvLocalPath()));

  // Layer 3: process environment (highest priority)
  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined) {
      merged[key] = value;
    }
  }

  // Ensure JWT_SECRET exists — generate and persist to user config if missing
  if (!merged['JWT_SECRET'] || merged['JWT_SECRET'] === 'ai_theme_jwt_secret_change_me') {
    merged['JWT_SECRET'] = generateJwtSecret();
    // Persist to user .env.local
    persistEnvLocal({ JWT_SECRET: merged['JWT_SECRET'] });
  }

  // Set defaults for required vars
  if (!merged['WEB_APP_READ_MODE']) merged['WEB_APP_READ_MODE'] = 'http';
  if (!merged['HF_HUB_OFFLINE']) merged['HF_HUB_OFFLINE'] = '1';

  return merged;
}

export function persistEnvLocal(updates: Record<string, string>): void {
  const envPath = userEnvLocalPath();
  let existing = '';
  if (fs.existsSync(envPath)) {
    existing = fs.readFileSync(envPath, 'utf-8');
  }
  const lines = existing.split('\n').filter(l => l.trim());
  const map = parseEnvFile(envPath);
  Object.assign(map, updates);
  const newContent = Object.entries(map)
    .map(([k, v]) => `${k}=${v}`)
    .join('\n') + '\n';
  fs.writeFileSync(envPath, newContent, 'utf-8');
}

export function getUserConfigDir(): string {
  return userConfigDir();
}

export function getUserEnvLocalPath(): string {
  return userEnvLocalPath();
}
