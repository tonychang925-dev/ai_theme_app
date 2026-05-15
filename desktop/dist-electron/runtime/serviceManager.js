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
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.startAll = startAll;
exports.stopAll = stopAll;
exports.getServiceStatus = getServiceStatus;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const http_1 = __importDefault(require("http"));
const electron_1 = require("electron");
const envLoader_1 = require("./envLoader");
const dependencyDoctor_1 = require("./dependencyDoctor");
const portManager_1 = require("./portManager");
const processTree_1 = require("./processTree");
const healthChecker_1 = require("./healthChecker");
const logManager_1 = require("./logManager");
let managedProcesses = new Map();
let redisStartedByUs = false;
let _cdProjectRoot = null; // retained for reference, CDP lifecycle delegated to web_app BFF
async function startAll(projectRoot) {
    _cdProjectRoot = projectRoot;
    // (cdProjectRoot kept for reference, CDP lifecycle delegated to web_app BFF)
    const userDataDir = path.dirname((0, logManager_1.getLogDir)()); // ~/Library/Application Support/AI投资助理
    (0, logManager_1.logInfo)('ServiceManager: ===== Starting all services =====');
    // 1. Load env
    const env = (0, envLoader_1.loadEnv)(projectRoot);
    const logDir = (0, logManager_1.getLogDir)();
    // Inject desktop runtime paths
    env['DESKTOP_LOG_DIR'] = logDir;
    env['DESKTOP_USER_DATA'] = userDataDir;
    // 2. Dependency doctor
    const doctor = await (0, dependencyDoctor_1.runDoctor)(projectRoot, env);
    (0, logManager_1.logInfo)(`ServiceManager: doctor passed=${doctor.pass}`);
    if (!doctor.pass) {
        (0, logManager_1.logError)('ServiceManager: dependency doctor failed, check diagnostics');
        return { success: false, webPort: 0, spsPort: 0, cdpPort: 0, doctorPassed: false, doctorChecks: doctor.checks, readyzResult: null };
    }
    // 3. Clear stale PIDs from previous runs
    (0, portManager_1.clearStalePids)();
    // 4. Ensure Redis (best effort)
    // Redis is handled in dependencyDoctor already
    // 5. Allocate ports
    const ports = (0, portManager_1.allocatePorts)({
        web: parseInt(env['WEB_PORT'] || '8000', 10),
        sps: parseInt(env['SPS_PORT'] || '8090', 10),
        cdp: parseInt(env['CDP_PORT'] || '8095', 10),
    });
    // 6. Determine Python paths
    const venvPython = path.join(projectRoot, '.venv', 'bin', 'python');
    const condaPython = '/opt/miniconda3/envs/theme_matcher_env/bin/python';
    // 7. Set env vars that services will read
    // CRITICAL: ensure JWT_SECRET is never empty — backend raises RuntimeError without it
    const jwtSecret = env['JWT_SECRET'] || (0, envLoader_1.generateJwtSecret)();
    if (!env['JWT_SECRET']) {
        (0, envLoader_1.persistEnvLocal)({ JWT_SECRET: jwtSecret });
    }
    const serviceEnv = {
        ...env,
        'JWT_SECRET': jwtSecret,
        'WEB_PORT': String(ports.web),
        'SPS_PORT': String(ports.sps),
        'CDP_PORT': String(ports.cdp),
        'STOCK_PROCESSING_READ_BASE_URL': `http://127.0.0.1:${ports.sps}`,
        'WEB_APP_READ_MODE': 'http',
        'HF_HUB_OFFLINE': '1',
        'PYTHONPATH': projectRoot,
    };
    // Set FRONTEND_DIST_DIR for web_app_service
    // V1-dev: projectRoot/frontend/dist
    // V1-app: extraResources path inside .app bundle
    if (!serviceEnv['FRONTEND_DIST_DIR']) {
        if (electron_1.app.isPackaged) {
            serviceEnv['FRONTEND_DIST_DIR'] = path.join(process.resourcesPath, 'frontend', 'dist');
        }
        else {
            serviceEnv['FRONTEND_DIST_DIR'] = path.join(projectRoot, 'frontend', 'dist');
        }
    }
    // 8. Start SPS
    (0, logManager_1.logInfo)(`ServiceManager: starting stock_processing_service on port ${ports.sps}`);
    const spsProc = (0, processTree_1.spawnCommand)(condaPython, [
        '-m', 'uvicorn',
        'stock_processing_service.api_app:app',
        '--host', '127.0.0.1',
        '--port', String(ports.sps),
    ], {
        cwd: projectRoot,
        env: { ...serviceEnv, 'REDIS_URL': serviceEnv['REDIS_URL'] || 'redis://localhost:6379/0' },
        logName: 'stock_processing_service.log',
    });
    managedProcesses.set('sps', { pid: spsProc.pid, port: ports.sps });
    (0, logManager_1.logInfo)('ServiceManager: waiting for SPS healthz...');
    const spsHealthy = await (0, healthChecker_1.waitForHealthz)(ports.sps);
    if (!spsHealthy) {
        (0, logManager_1.logError)('ServiceManager: SPS failed to become healthy');
        await stopAll();
        return { success: false, webPort: ports.web, spsPort: ports.sps, cdpPort: ports.cdp, doctorPassed: true, doctorChecks: null, readyzResult: null };
    }
    (0, logManager_1.logInfo)('ServiceManager: SPS healthy');
    // 9. Start web_app_service
    (0, logManager_1.logInfo)(`ServiceManager: starting web_app_service on port ${ports.web}`);
    const webProc = (0, processTree_1.spawnCommand)(venvPython, [
        '-m', 'uvicorn',
        'web_app_service.main:app',
        '--host', '0.0.0.0',
        '--port', String(ports.web),
    ], {
        cwd: projectRoot,
        env: {
            ...serviceEnv,
            'STOCK_PROCESSING_READ_BASE_URL': `http://127.0.0.1:${ports.sps}`,
            'FRONTEND_DIST_DIR': serviceEnv['FRONTEND_DIST_DIR'],
        },
        logName: 'web_app_service.log',
    });
    managedProcesses.set('web', { pid: webProc.pid, port: ports.web });
    (0, logManager_1.logInfo)('ServiceManager: waiting for web_app healthz...');
    const webHealthy = await (0, healthChecker_1.waitForHealthz)(ports.web, '127.0.0.1');
    if (!webHealthy) {
        (0, logManager_1.logError)('ServiceManager: web_app_service failed to become healthy');
        await stopAll();
        return { success: false, webPort: ports.web, spsPort: ports.sps, cdpPort: ports.cdp, doctorPassed: true, doctorChecks: null, readyzResult: null };
    }
    (0, logManager_1.logInfo)('ServiceManager: web_app healthy');
    // 10. Wait for readyz
    (0, logManager_1.logInfo)('ServiceManager: waiting for readyz...');
    const readyzResult = await (0, healthChecker_1.waitForReadyz)(ports.web);
    if (!readyzResult || readyzResult.status === 'failed') {
        (0, logManager_1.logError)(`ServiceManager: readyz failed status=${readyzResult?.status}`);
        // Don't stop — degraded still allows the app to show
        if (readyzResult?.status === 'failed') {
            await stopAll();
            return { success: false, webPort: ports.web, spsPort: ports.sps, cdpPort: ports.cdp, doctorPassed: true, doctorChecks: null, readyzResult };
        }
    }
    // 11. CDP service: ENABLE_CDP is deprecated.
    // JYHF CDP must be started only by web_app JyhfCdpManager via the UI console.
    // Direct Electron spawn would create a second lifecycle manager and cause conflicts.
    // 12. Verify e2e
    const e2eOk = await (0, healthChecker_1.verifyE2E)(ports.web);
    (0, logManager_1.logInfo)(`ServiceManager: e2e verification ${e2eOk ? 'OK' : 'FAILED'}`);
    // Save PIDs
    const pidRecords = Array.from(managedProcesses.entries())
        .filter(([, v]) => v.pid)
        .map(([k, v]) => ({
        serviceName: k,
        pid: v.pid,
        port: v.port,
        startedAt: new Date().toISOString(),
    }));
    (0, portManager_1.savePids)(pidRecords);
    (0, logManager_1.logInfo)('ServiceManager: ===== All services started =====');
    return {
        success: true,
        webPort: ports.web,
        spsPort: ports.sps,
        cdpPort: ports.cdp,
        doctorPassed: doctor.pass,
        doctorChecks: doctor.checks,
        readyzResult,
    };
}
async function stopAll() {
    (0, logManager_1.logInfo)('ServiceManager: ===== Stopping all services =====');
    // CDP lifecycle is managed by web_app BFF (JyhfCdpManager).
    // Delegate via the /api/v2/realtime/jyhf-cdp/service/stop endpoint.
    // This respects owner=managed vs owner=external: only managed gets killed.
    if (_cdProjectRoot) {
        try {
            await _httpPost('127.0.0.1', 8000, '/api/v2/realtime/jyhf-cdp/service/stop', 5000);
            (0, logManager_1.logInfo)('ServiceManager: CDP stop delegated to web_app BFF');
        }
        catch {
            (0, logManager_1.logInfo)('ServiceManager: CDP service stop request failed (web_app may be down)');
        }
    }
    await (0, processTree_1.killAllManaged)(5000);
    // Only stop Redis if we started it
    if (redisStartedByUs) {
        (0, logManager_1.logInfo)('ServiceManager: stopping Redis (started by us)');
        try {
            const { execSync } = require('child_process');
            execSync('brew services stop redis', { timeout: 10000 });
        }
        catch {
            (0, logManager_1.logError)('ServiceManager: failed to stop Redis');
        }
    }
    // Clear PID state (keep logs)
    const pidsPath = path.join(path.dirname((0, logManager_1.getLogDir)()), 'runtime', 'pids.json');
    try {
        fs.writeFileSync(pidsPath, '[]', 'utf-8');
    }
    catch { }
    managedProcesses.clear();
    (0, logManager_1.logInfo)('ServiceManager: ===== All services stopped =====');
}
function _httpPost(host, port, pathStr, timeoutMs) {
    return new Promise((resolve, reject) => {
        const req = http_1.default.request({
            hostname: host, port, path: pathStr, method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            timeout: timeoutMs,
        }, (res) => {
            res.resume();
            res.on('end', resolve);
        });
        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
        req.write('{}');
        req.end();
    });
}
function getServiceStatus() {
    return Array.from(managedProcesses.entries()).map(([name, info]) => ({
        name,
        running: !!info.pid,
        port: info.port,
        pid: info.pid,
    }));
}
//# sourceMappingURL=serviceManager.js.map