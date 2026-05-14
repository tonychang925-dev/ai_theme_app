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
exports.getLogDir = getLogDir;
exports.rotateLog = rotateLog;
exports.logInfo = logInfo;
exports.logError = logError;
exports.exportDiagnostics = exportDiagnostics;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const electron_1 = require("electron");
const MAX_LOG_SIZE = 10 * 1024 * 1024; // 10 MB
const MAX_LOG_FILES = 5;
function getLogDir() {
    const dir = path.join(electron_1.app.getPath('userData'), 'logs');
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
    return dir;
}
function rotateLog(logName) {
    const logPath = path.join(getLogDir(), logName);
    if (fs.existsSync(logPath) && fs.statSync(logPath).size > MAX_LOG_SIZE) {
        for (let i = MAX_LOG_FILES - 1; i >= 0; i--) {
            const oldPath = i === 0 ? logPath : `${logPath}.${i}`;
            const newPath = `${logPath}.${i + 1}`;
            if (fs.existsSync(oldPath)) {
                if (i === MAX_LOG_FILES - 1) {
                    fs.unlinkSync(oldPath);
                }
                else {
                    fs.renameSync(oldPath, newPath);
                }
            }
        }
        fs.renameSync(logPath, `${logPath}.1`);
    }
    return logPath;
}
function logInfo(message) {
    const ts = new Date().toISOString();
    const line = `[${ts}] [INFO] ${message}\n`;
    const logPath = rotateLog('desktop-main.log');
    fs.appendFileSync(logPath, line, 'utf-8');
}
function logError(message) {
    const ts = new Date().toISOString();
    const line = `[${ts}] [ERROR] ${message}\n`;
    const logPath = rotateLog('desktop-main.log');
    fs.appendFileSync(logPath, line, 'utf-8');
}
function exportDiagnostics() {
    // Create a timestamped directory with copies of all logs and runtime state
    const outputDir = path.join(electron_1.app.getPath('userData'), 'diagnostics');
    if (!fs.existsSync(outputDir)) {
        fs.mkdirSync(outputDir, { recursive: true });
    }
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const exportDir = path.join(outputDir, `diagnostics-${ts}`);
    fs.mkdirSync(exportDir, { recursive: true });
    // Copy log files
    const logDir = getLogDir();
    if (fs.existsSync(logDir)) {
        const logsDir = path.join(exportDir, 'logs');
        fs.mkdirSync(logsDir, { recursive: true });
        for (const f of fs.readdirSync(logDir)) {
            fs.copyFileSync(path.join(logDir, f), path.join(logsDir, f));
        }
    }
    // Copy runtime state
    const runtimeDir = path.join(electron_1.app.getPath('userData'), 'runtime');
    if (fs.existsSync(runtimeDir)) {
        const rtDir = path.join(exportDir, 'runtime');
        fs.mkdirSync(rtDir, { recursive: true });
        for (const f of fs.readdirSync(runtimeDir)) {
            fs.copyFileSync(path.join(runtimeDir, f), path.join(rtDir, f));
        }
    }
    // Copy config (sanitize secrets)
    const configDir = path.join(electron_1.app.getPath('userData'), 'config');
    if (fs.existsSync(configDir)) {
        const cfgDir = path.join(exportDir, 'config');
        fs.mkdirSync(cfgDir, { recursive: true });
        for (const f of fs.readdirSync(configDir)) {
            const content = fs.readFileSync(path.join(configDir, f), 'utf-8');
            // Redact sensitive values
            const sanitized = content.replace(/(DEEPSEEK_API_KEY|TUSHARE_TOKEN|JWT_SECRET|DATABASE_URL|password)=.+/gi, '$1=***REDACTED***');
            fs.writeFileSync(path.join(cfgDir, f), sanitized, 'utf-8');
        }
    }
    electron_1.shell.showItemInFolder(exportDir);
    return exportDir;
}
//# sourceMappingURL=logManager.js.map