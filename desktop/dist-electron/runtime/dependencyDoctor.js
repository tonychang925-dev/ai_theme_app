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
function runDoctor(projectRoot, env) {
    const checks = [];
    // 1. Python venv for web_app_service
    const venvPython = path.join(projectRoot, '.venv', 'bin', 'python');
    if (fs.existsSync(venvPython)) {
        try {
            const ver = (0, child_process_1.execSync)(`"${venvPython}" --version`, { encoding: 'utf-8', timeout: 5000 }).trim();
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
            const ver = (0, child_process_1.execSync)(`"${condaPython}" --version`, { encoding: 'utf-8', timeout: 5000 }).trim();
            checks.push({ name: 'python_conda', status: 'pass', message: ver });
        }
        catch {
            checks.push({ name: 'python_conda', status: 'fail', message: 'conda python not runnable', fixHint: 'conda create -n theme_matcher_env python=3.12' });
        }
    }
    else {
        checks.push({ name: 'python_conda', status: 'fail', message: `conda env not found at ${condaPython}`, fixHint: 'conda create -n theme_matcher_env python=3.12' });
    }
    // 3. PostgreSQL connection
    const dbUrl = env['DATABASE_URL'] || '';
    if (dbUrl) {
        try {
            (0, child_process_1.execSync)(`${venvPython} -c "
import asyncpg, asyncio
async def t():
    conn = await asyncpg.connect('${dbUrl}', timeout=5)
    await conn.fetchval('SELECT 1')
    await conn.close()
asyncio.run(t())
"`, { encoding: 'utf-8', timeout: 10000, cwd: projectRoot });
            checks.push({ name: 'postgresql', status: 'pass', message: 'connected' });
        }
        catch {
            checks.push({ name: 'postgresql', status: 'fail', message: 'cannot connect to PostgreSQL', fixHint: 'Ensure PostgreSQL is running and DATABASE_URL is correct' });
        }
    }
    else {
        checks.push({ name: 'postgresql', status: 'warn', message: 'DATABASE_URL not configured' });
    }
    // 4. Redis
    try {
        (0, child_process_1.execSync)('redis-cli ping', { encoding: 'utf-8', timeout: 5000 });
        checks.push({ name: 'redis', status: 'pass', message: 'redis-cli ping OK' });
    }
    catch {
        // Try starting via brew
        try {
            (0, child_process_1.execSync)('brew services start redis', { timeout: 10000 });
            (0, child_process_1.execSync)('redis-cli ping', { encoding: 'utf-8', timeout: 5000 });
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