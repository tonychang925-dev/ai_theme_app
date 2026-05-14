"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.generateJwtSecret = generateJwtSecret;
exports.loadEnv = loadEnv;
exports.persistEnvLocal = persistEnvLocal;
exports.getUserConfigDir = getUserConfigDir;
exports.getUserEnvLocalPath = getUserEnvLocalPath;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const electron_1 = require("electron");
function userConfigDir() {
    return path.join(electron_1.app.getPath('userData'), 'config');
}
function userEnvLocalPath() {
    return path.join(userConfigDir(), '.env.local');
}
function generateJwtSecret() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-';
    let result = '';
    for (let i = 0; i < 64; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}
function parseEnvFile(filePath) {
    const result = {};
    if (!fs.existsSync(filePath))
        return result;
    const content = fs.readFileSync(filePath, 'utf-8');
    for (const raw of content.split('\n')) {
        const line = raw.trim();
        if (!line || line.startsWith('#') || !line.includes('='))
            continue;
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
function loadEnv(projectRoot) {
    const merged = {};
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
    if (!merged['WEB_APP_READ_MODE'])
        merged['WEB_APP_READ_MODE'] = 'http';
    if (!merged['HF_HUB_OFFLINE'])
        merged['HF_HUB_OFFLINE'] = '1';
    return merged;
}
function persistEnvLocal(updates) {
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
function getUserConfigDir() {
    return userConfigDir();
}
function getUserEnvLocalPath() {
    return userEnvLocalPath();
}
//# sourceMappingURL=envLoader.js.map