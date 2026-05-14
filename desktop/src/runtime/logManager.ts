import * as fs from 'fs';
import * as path from 'path';
import { app, shell } from 'electron';

const MAX_LOG_SIZE = 10 * 1024 * 1024; // 10 MB
const MAX_LOG_FILES = 5;

export function getLogDir(): string {
  const dir = path.join(app.getPath('userData'), 'logs');
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return dir;
}

export function rotateLog(logName: string): string {
  const logPath = path.join(getLogDir(), logName);
  if (fs.existsSync(logPath) && fs.statSync(logPath).size > MAX_LOG_SIZE) {
    for (let i = MAX_LOG_FILES - 1; i >= 0; i--) {
      const oldPath = i === 0 ? logPath : `${logPath}.${i}`;
      const newPath = `${logPath}.${i + 1}`;
      if (fs.existsSync(oldPath)) {
        if (i === MAX_LOG_FILES - 1) {
          fs.unlinkSync(oldPath);
        } else {
          fs.renameSync(oldPath, newPath);
        }
      }
    }
    fs.renameSync(logPath, `${logPath}.1`);
  }
  return logPath;
}

export function logInfo(message: string): void {
  const ts = new Date().toISOString();
  const line = `[${ts}] [INFO] ${message}\n`;
  const logPath = rotateLog('desktop-main.log');
  fs.appendFileSync(logPath, line, 'utf-8');
}

export function logError(message: string): void {
  const ts = new Date().toISOString();
  const line = `[${ts}] [ERROR] ${message}\n`;
  const logPath = rotateLog('desktop-main.log');
  fs.appendFileSync(logPath, line, 'utf-8');
}

export function exportDiagnostics(): string {
  // Create a timestamped directory with copies of all logs and runtime state
  const outputDir = path.join(app.getPath('userData'), 'diagnostics');
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
  const runtimeDir = path.join(app.getPath('userData'), 'runtime');
  if (fs.existsSync(runtimeDir)) {
    const rtDir = path.join(exportDir, 'runtime');
    fs.mkdirSync(rtDir, { recursive: true });
    for (const f of fs.readdirSync(runtimeDir)) {
      fs.copyFileSync(path.join(runtimeDir, f), path.join(rtDir, f));
    }
  }

  // Copy config (sanitize secrets)
  const configDir = path.join(app.getPath('userData'), 'config');
  if (fs.existsSync(configDir)) {
    const cfgDir = path.join(exportDir, 'config');
    fs.mkdirSync(cfgDir, { recursive: true });
    for (const f of fs.readdirSync(configDir)) {
      const content = fs.readFileSync(path.join(configDir, f), 'utf-8');
      // Redact sensitive values
      const sanitized = content.replace(
        /(DEEPSEEK_API_KEY|TUSHARE_TOKEN|JWT_SECRET|DATABASE_URL|password)=.+/gi,
        '$1=***REDACTED***',
      );
      fs.writeFileSync(path.join(cfgDir, f), sanitized, 'utf-8');
    }
  }

  shell.showItemInFolder(exportDir);
  return exportDir;
}
