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
exports.spawnCommand = spawnCommand;
exports.killProcessTree = killProcessTree;
exports.killAllManaged = killAllManaged;
const child_process_1 = require("child_process");
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const logManager_1 = require("./logManager");
const KNOWN_PROCESSES = [];
function spawnCommand(command, args, opts) {
    const logPath = opts.env['DESKTOP_LOG_DIR'] || '';
    const logFile = path.join(logPath, opts.logName);
    const outFd = fs.openSync(logFile, 'a');
    (0, logManager_1.logInfo)(`ProcessTree: spawning ${command} ${args.join(' ')}`);
    const child = (0, child_process_1.spawn)(command, args, {
        cwd: opts.cwd,
        env: { ...process.env, ...opts.env },
        detached: true,
        stdio: ['ignore', outFd, outFd],
    });
    child.on('error', (err) => {
        (0, logManager_1.logError)(`ProcessTree: ${opts.logName} spawn error: ${err.message}`);
    });
    child.on('exit', (code, signal) => {
        (0, logManager_1.logInfo)(`ProcessTree: ${opts.logName} exited code=${code} signal=${signal}`);
        fs.closeSync(outFd);
    });
    KNOWN_PROCESSES.push({ child, name: opts.logName });
    return child;
}
function killProcessTree(name, timeoutMs = 5000) {
    const entry = KNOWN_PROCESSES.find(p => p.name === name);
    if (!entry || !entry.child.pid) {
        (0, logManager_1.logInfo)(`ProcessTree: no process "${name}" to kill`);
        return Promise.resolve();
    }
    const pid = entry.child.pid;
    (0, logManager_1.logInfo)(`ProcessTree: killing process group for "${name}" (PGID=${pid})`);
    return new Promise((resolve) => {
        try {
            // Kill the entire process group (negative PID)
            process.kill(-pid, 'SIGTERM');
        }
        catch (e) {
            (0, logManager_1.logError)(`ProcessTree: SIGTERM failed for ${pid}: ${e}`);
        }
        const forceKillTimeout = setTimeout(() => {
            (0, logManager_1.logInfo)(`ProcessTree: force killing "${name}" (PGID=${-pid})`);
            try {
                process.kill(-pid, 'SIGKILL');
            }
            catch (e) {
                (0, logManager_1.logError)(`ProcessTree: SIGKILL failed for ${pid}: ${e}`);
            }
            resolve();
        }, timeoutMs);
        entry.child.once('exit', () => {
            clearTimeout(forceKillTimeout);
            (0, logManager_1.logInfo)(`ProcessTree: "${name}" exited gracefully`);
            resolve();
        });
    });
}
async function killAllManaged(timeoutMs = 5000) {
    // Stop in reverse order: CDP → web_app → SPS
    const order = ['jyhf_cdp_service.log', 'web_app_service.log', 'stock_processing_service.log'];
    for (const name of order) {
        await killProcessTree(name, timeoutMs);
    }
    KNOWN_PROCESSES.length = 0;
}
//# sourceMappingURL=processTree.js.map