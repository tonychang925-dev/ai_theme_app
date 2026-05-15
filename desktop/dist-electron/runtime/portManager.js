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
exports.killProjectProcessesOnDefaultPorts = killProjectProcessesOnDefaultPorts;
exports.loadPreviousPids = loadPreviousPids;
exports.savePids = savePids;
exports.savePorts = savePorts;
exports.loadPreviousPorts = loadPreviousPorts;
exports.allocatePorts = allocatePorts;
exports.clearStalePids = clearStalePids;
exports.getRuntimeDir = getRuntimeDir;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const child_process_1 = require("child_process");
const electron_1 = require("electron");
const logManager_1 = require("./logManager");
const DEFAULT_PORTS = { web: 8000, sps: 8090, cdp: 8095 };
const FALLBACK_RANGES = {
    web: [8100, 8199],
    sps: [8200, 8299],
    cdp: [8300, 8399],
};
function runtimeDir() {
    const dir = path.join(electron_1.app.getPath('userData'), 'runtime');
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
    return dir;
}
function pidsFilePath() {
    return path.join(runtimeDir(), 'pids.json');
}
function portsFilePath() {
    return path.join(runtimeDir(), 'ports.json');
}
function isPortInUse(port) {
    try {
        const out = (0, child_process_1.execSync)(`lsof -nP -iTCP:${port} -sTCP:LISTEN -t`, { encoding: 'utf-8', timeout: 3000 }).trim();
        return out.length > 0;
    }
    catch {
        return false;
    }
}
/** Check if a PID belongs to this project by inspecting its command line. */
function isProjectProcess(pid) {
    const markers = [
        'ai_theme_app',
        'web_app_service.main:app',
        'stock_processing_service',
        'services.jyhf_cdp_service.app:app',
    ];
    try {
        const cmdline = (0, child_process_1.execSync)(`ps -p ${pid} -o args=`, { encoding: 'utf-8', timeout: 3000 }).trim();
        return markers.some(m => cmdline.includes(m));
    }
    catch {
        return false;
    }
}
/** Get all PIDs listening on a port. */
function getPidsOnPort(port) {
    try {
        const out = (0, child_process_1.execSync)(`lsof -nP -iTCP:${port} -sTCP:LISTEN -t`, { encoding: 'utf-8', timeout: 3000 }).trim();
        return out.split('\n').filter(Boolean).map(Number);
    }
    catch {
        return [];
    }
}
/**
 * Scan default ports and kill any process that belongs to this project.
 * Returns a list of killed ports.
 */
function killProjectProcessesOnDefaultPorts(projectRoot) {
    const killed = [];
    for (const [serviceName, port] of Object.entries(DEFAULT_PORTS)) {
        const pids = getPidsOnPort(port);
        for (const pid of pids) {
            if (isProjectProcess(pid)) {
                (0, logManager_1.logInfo)(`PortManager: killing project process pid=${pid} on port ${port} (${serviceName})`);
                try {
                    // Kill process group
                    try {
                        process.kill(-pid, 'SIGTERM');
                    }
                    catch {
                        process.kill(pid, 'SIGTERM');
                    }
                    // Wait for port release
                    const deadline = Date.now() + 5000;
                    while (Date.now() < deadline) {
                        if (!isPortInUse(port))
                            break;
                        const end = Date.now() + 200;
                        while (Date.now() < end) { /* spin */ }
                    }
                    // Force kill if still alive
                    if (isPortInUse(port)) {
                        (0, logManager_1.logInfo)(`PortManager: force-killing stubborn process on port ${port}`);
                        try {
                            process.kill(-pid, 'SIGKILL');
                        }
                        catch {
                            process.kill(pid, 'SIGKILL');
                        }
                        const end = Date.now() + 1000;
                        while (Date.now() < end) { /* spin */ }
                    }
                    killed.push(port);
                }
                catch (e) {
                    (0, logManager_1.logInfo)(`PortManager: failed to kill pid=${pid}: ${e}`);
                }
            }
            else {
                (0, logManager_1.logInfo)(`PortManager: port ${port} occupied by non-project pid=${pid}, not killing`);
            }
        }
    }
    return killed;
}
function loadPreviousPids() {
    const f = pidsFilePath();
    if (!fs.existsSync(f))
        return [];
    try {
        return JSON.parse(fs.readFileSync(f, 'utf-8'));
    }
    catch {
        return [];
    }
}
function savePids(records) {
    fs.writeFileSync(pidsFilePath(), JSON.stringify(records, null, 2), 'utf-8');
}
function savePorts(allocation) {
    fs.writeFileSync(portsFilePath(), JSON.stringify(allocation, null, 2), 'utf-8');
}
function loadPreviousPorts() {
    const f = portsFilePath();
    if (!fs.existsSync(f))
        return null;
    try {
        return JSON.parse(fs.readFileSync(f, 'utf-8'));
    }
    catch {
        return null;
    }
}
function allocatePorts(envPorts, projectRoot) {
    const result = { ...DEFAULT_PORTS };
    // Apply env overrides
    if (envPorts.web)
        result.web = envPorts.web;
    if (envPorts.sps)
        result.sps = envPorts.sps;
    if (envPorts.cdp)
        result.cdp = envPorts.cdp;
    // First pass: clean up project-owned processes on default ports
    // This prevents new instances from using fallback ports when old ones linger
    if (projectRoot) {
        killProjectProcessesOnDefaultPorts(projectRoot);
    }
    // Check each port, fallback only for non-project processes
    for (const key of ['web', 'sps', 'cdp']) {
        if (isPortInUse(result[key])) {
            const pids = getPidsOnPort(result[key]);
            const isProject = pids.some(p => isProjectProcess(p));
            if (isProject) {
                // Should not happen after cleanup, but just in case
                (0, logManager_1.logInfo)(`PortManager: ${key} port ${result[key]} still occupied by project process after cleanup, retrying...`);
                killProjectProcessesOnDefaultPorts(projectRoot || '');
                // Wait
                const end = Date.now() + 2000;
                while (Date.now() < end) { /* spin */ }
            }
            if (isPortInUse(result[key])) {
                const [start, end] = FALLBACK_RANGES[key];
                let found = false;
                for (let p = start; p <= end; p++) {
                    if (!isPortInUse(p)) {
                        (0, logManager_1.logInfo)(`PortManager: ${key} port ${result[key]} in use (non-project), using fallback ${p}`);
                        result[key] = p;
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    (0, logManager_1.logError)(`PortManager: no available port for ${key} in range ${start}-${end}`);
                    throw new Error(`No available port for ${key}`);
                }
            }
        }
    }
    savePorts(result);
    return result;
}
function clearStalePids() {
    const records = loadPreviousPids();
    const alive = [];
    for (const rec of records) {
        try {
            process.kill(rec.pid, 0); // Signal 0 checks existence
            (0, logManager_1.logInfo)(`PortManager: stale PID ${rec.pid} (${rec.serviceName}:${rec.port}) still alive, cleaning up...`);
            // Kill the process group
            try {
                process.kill(-rec.pid, 'SIGTERM');
            }
            catch {
                // May fail if we don't have permission, try direct kill
                try {
                    process.kill(rec.pid, 'SIGTERM');
                }
                catch { }
            }
            // Wait briefly
            const start = Date.now();
            let dead = false;
            while (Date.now() - start < 3000) {
                try {
                    process.kill(rec.pid, 0);
                }
                catch {
                    dead = true;
                    break;
                }
                // busy-wait is bad, use a sync sleep workaround
                const end = Date.now() + 50;
                while (Date.now() < end) { /* spin */ }
            }
            if (!dead) {
                try {
                    process.kill(-rec.pid, 'SIGKILL');
                }
                catch { }
                try {
                    process.kill(rec.pid, 'SIGKILL');
                }
                catch { }
                (0, logManager_1.logInfo)(`PortManager: force-killed stale PID ${rec.pid}`);
            }
            else {
                (0, logManager_1.logInfo)(`PortManager: stale PID ${rec.pid} terminated gracefully`);
            }
        }
        catch {
            (0, logManager_1.logInfo)(`PortManager: stale PID ${rec.pid} (${rec.serviceName}:${rec.port}) already dead, removing`);
            continue;
        }
        // Don't keep it in pids.json — it's been killed
    }
    savePids(alive);
}
function getRuntimeDir() {
    return runtimeDir();
}
//# sourceMappingURL=portManager.js.map