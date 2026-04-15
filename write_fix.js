/**
 * Write工具紧急修复包装器
 * 自动将相对路径转换为绝对路径
 */

const fs = require('fs');
const path = require('path');

// 项目根目录 - 硬编码确保正确
const PROJECT_ROOT = '/Users/admin/Desktop/ai_theme_app';

/**
 * 将相对路径转换为绝对路径
 * @param {string} filePath - 文件路径（相对或绝对）
 * @returns {string} 绝对路径
 */
function resolveFilePath(filePath) {
    // 如果已经是绝对路径，直接返回
    if (path.isAbsolute(filePath)) {
        return filePath;
    }

    // 如果是相对路径，基于项目根目录解析
    const resolvedPath = path.resolve(PROJECT_ROOT, filePath);

    console.log(`路径转换: "${filePath}" -> "${resolvedPath}"`);
    return resolvedPath;
}

/**
 * 修复Write工具参数
 * @param {object} params - Write工具参数
 * @returns {object} 修复后的参数
 */
function fixWriteParams(params) {
    if (!params || typeof params !== 'object') {
        return params;
    }

    const fixedParams = { ...params };

    // 修复file_path参数
    if (fixedParams.file_path && typeof fixedParams.file_path === 'string') {
        fixedParams.file_path = resolveFilePath(fixedParams.file_path);
    }

    return fixedParams;
}

/**
 * 直接写入文件（绕过Claude Code Write工具）
 * @param {string} filePath - 文件路径
 * @param {string} content - 文件内容
 */
function directWriteFile(filePath, content) {
    try {
        const resolvedPath = resolveFilePath(filePath);

        // 确保目录存在
        const dir = path.dirname(resolvedPath);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
            console.log(`创建目录: ${dir}`);
        }

        // 写入文件
        fs.writeFileSync(resolvedPath, content, 'utf8');
        console.log(`文件写入成功: ${resolvedPath}`);
        return { success: true, path: resolvedPath };
    } catch (error) {
        console.error(`文件写入失败: ${error.message}`);
        return { success: false, error: error.message };
    }
}

// 导出函数
module.exports = {
    resolveFilePath,
    fixWriteParams,
    directWriteFile,
    PROJECT_ROOT
};
