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
function allocatePorts(envPorts) {
    const result = { ...DEFAULT_PORTS };
    // Apply env overrides
    if (envPorts.web)
        result.web = envPorts.web;
    if (envPorts.sps)
        result.sps = envPorts.sps;
    if (envPorts.cdp)
        result.cdp = envPorts.cdp;
    // Check each port, fallback if needed
    for (const key of ['web', 'sps', 'cdp']) {
        if (isPortInUse(result[key])) {
            const [start, end] = FALLBACK_RANGES[key];
            let found = false;
            for (let p = start; p <= end; p++) {
                if (!isPortInUse(p)) {
                    (0, logManager_1.logInfo)(`PortManager: ${key} port ${result[key]} in use, using fallback ${p}`);
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
    savePorts(result);
    return result;
}
function clearStalePids() {
    const records = loadPreviousPids();
    const alive = [];
    for (const rec of records) {
        try {
            process.kill(rec.pid, 0); // Signal 0 just checks existence
            (0, logManager_1.logInfo)(`PortManager: stale PID ${rec.pid} (${rec.serviceName}:${rec.port}) still alive, will clean up`);
        }
        catch {
            (0, logManager_1.logInfo)(`PortManager: stale PID ${rec.pid} (${rec.serviceName}:${rec.port}) already dead, removing`);
            continue;
        }
        alive.push(rec);
    }
    savePids(alive);
}
function getRuntimeDir() {
    return runtimeDir();
}
//# sourceMappingURL=portManager.js.map