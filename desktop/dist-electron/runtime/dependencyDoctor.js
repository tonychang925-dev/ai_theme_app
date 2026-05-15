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
exports.runDoctor = runDoctor;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const child_process_1 = require("child_process");
/** Run a shell command with a timeout. Returns stdout or throws. */
function execAsync(command, timeoutMs = 5000) {
    return new Promise((resolve, reject) => {
        const child = (0, child_process_1.exec)(command, { encoding: 'utf-8', timeout: timeoutMs }, (err, stdout) => {
            if (err) {
                reject(err);
            }
            else {
                resolve(stdout.trim());
            }
        });
        // exec's built-in timeout sends SIGTERM; this is a safety net
        const timer = setTimeout(() => {
            child.kill('SIGKILL');
            reject(new Error(`Command timed out after ${timeoutMs}ms`));
        }, timeoutMs + 2000);
        child.on('close', () => clearTimeout(timer));
    });
}
async function runDoctor(projectRoot, env) {
    const checks = [];
    // 1. Python venv for web_app_service
    const venvPython = path.join(projectRoot, '.venv', 'bin', 'python');
    if (fs.existsSync(venvPython)) {
        try {
            const ver = await execAsync(`"${venvPython}" --version`, 5000);
            checks.push({ name: 'python_venv', status: 'pass', message: ver });
        }
        catch {
            checks.push({ name: 'python_venv', status: 'fail', message: 'venv python not runnable', fixHint: `cd ${projectRoot} && python3 -m venv .venv` });
        }
    }
    else {
        checks.push({ name: 'python_venv', status: 'fail', message: '.venv/bin/python not found', fixHint: `cd ${projectRoot} && python3 -m venv .venv` });
    }
    // 2. Python conda for stock_processing_service
    const condaPython = '/opt/miniconda3/envs/theme_matcher_env/bin/python';
    if (fs.existsSync(condaPython)) {
        try {
            const ver = await execAsync(`"${condaPython}" --version`, 5000);
            checks.push({ name: 'python_conda', status: 'pass', message: ver });
        }
        catch {
            checks.push({ name: 'python_conda', status: 'fail', message: 'conda python not runnable', fixHint: 'conda create -n theme_matcher_env python=3.12' });
        }
    }
    else {
        checks.push({ name: 'python_conda', status: 'fail', message: `conda env not found at ${condaPython}`, fixHint: 'conda create -n theme_matcher_env python=3.12' });
    }
    // 3. PostgreSQL connection — with stale lock auto-recovery
    const pgDataDir = '/usr/local/var/postgresql@14';
    const pgPidFile = path.join(pgDataDir, 'postmaster.pid');
    async function checkPostgresConnection() {
        try {
            await execAsync(`"${venvPython}" -c "
import socket
s = socket.socket()
s.settimeout(3)
s.connect(('localhost', 5432))
s.close()
"`, 5000);
            return { ok: true, detail: 'TCP localhost:5432 OK' };
        }
        catch {
            return { ok: false, detail: 'TCP localhost:5432 not reachable' };
        }
    }
    let pgResult = await checkPostgresConnection();
    if (!pgResult.ok) {
        // Check for stale postmaster.pid and auto-recover
        if (fs.existsSync(pgPidFile)) {
            try {
                const pidContent = fs.readFileSync(pgPidFile, 'utf-8');
                const recordedPid = parseInt(pidContent.split('\n')[0], 10);
                if (recordedPid && !isNaN(recordedPid)) {
                    try {
                        const commOut = await execAsync(`ps -p ${recordedPid} -o comm= 2>/dev/null || true`, 3000);
                        if (!commOut.includes('postgres')) {
                            // PID is not postgres — stale lock, clean and retry
                            fs.unlinkSync(pgPidFile);
                            await execAsync('brew services start postgresql@14', 15000);
                            // Retry connection
                            await new Promise(r => setTimeout(r, 3000));
                            pgResult = await checkPostgresConnection();
                        }
                    }
                    catch {
                        // ps command failed → PID likely dead, stale lock
                        fs.unlinkSync(pgPidFile);
                        await execAsync('brew services start postgresql@14', 15000);
                        await new Promise(r => setTimeout(r, 3000));
                        pgResult = await checkPostgresConnection();
                    }
                }
            }
            catch {
                // Can't read/parse pid file — try starting anyway
                try {
                    await execAsync('brew services start postgresql@14', 15000);
                }
                catch { }
                await new Promise(r => setTimeout(r, 3000));
                pgResult = await checkPostgresConnection();
            }
        }
        else {
            // No lock file — PostgreSQL simply not running, try starting
            try {
                await execAsync('brew services start postgresql@14', 15000);
            }
            catch { }
            await new Promise(r => setTimeout(r, 3000));
            pgResult = await checkPostgresConnection();
        }
    }
    if (pgResult.ok) {
        checks.push({ name: 'postgresql', status: 'pass', message: pgResult.detail });
    }
    else {
        checks.push({
            name: 'postgresql',
            status: 'fail',
            message: 'PostgreSQL not reachable after recovery attempt',
            fixHint: `Check log: tail -20 /usr/local/var/log/postgresql@14.log`,
        });
    }
    // 4. Redis
    try {
        await execAsync('redis-cli ping', 5000);
        checks.push({ name: 'redis', status: 'pass', message: 'redis-cli ping OK' });
    }
    catch {
        // Try starting via brew
        try {
            await execAsync('brew services start redis', 10000);
            await execAsync('redis-cli ping', 5000);
            checks.push({ name: 'redis', status: 'pass', message: 'started via brew services' });
        }
        catch {
            checks.push({ name: 'redis', status: 'warn', message: 'redis not available (degraded)', fixHint: 'brew install redis && brew services start redis' });
        }
    }
    // 5. Frontend dist
    const distDir = env['FRONTEND_DIST_DIR'] || path.join(projectRoot, 'frontend', 'dist');
    const indexHtml = path.join(distDir, 'index.html');
    if (fs.existsSync(indexHtml)) {
        checks.push({ name: 'frontend_dist', status: 'pass', message: distDir });
    }
    else {
        checks.push({ name: 'frontend_dist', status: 'fail', message: 'index.html not found', fixHint: `cd ${path.join(projectRoot, 'frontend')} && npm run build` });
    }
    // 6. Disk space
    try {
        const stat = fs.statfsSync('/tmp');
        const freeGB = (stat.bsize * stat.bfree) / (1024 * 1024 * 1024);
        if (freeGB < 0.5) {
            checks.push({ name: 'disk_space', status: 'warn', message: `only ${freeGB.toFixed(1)} GB free`, fixHint: 'Free up disk space' });
        }
        else {
            checks.push({ name: 'disk_space', status: 'pass', message: `${freeGB.toFixed(1)} GB free` });
        }
    }
    catch {
        checks.push({ name: 'disk_space', status: 'warn', message: 'could not check' });
    }
    const allPass = checks.every(c => c.status !== 'fail');
    return { pass: allPass, checks };
}
//# sourceMappingURL=dependencyDoctor.js.map