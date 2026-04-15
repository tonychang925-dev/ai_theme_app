// 调试脚本：检查IntelHeader组件
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const intelHeaderPath = path.join(__dirname, 'src/components/intel/IntelHeader.tsx');
const intelPagePath = path.join(__dirname, 'src/routes/intel/IntelPage.tsx');
const appPath = path.join(__dirname, 'src/App.tsx');

console.log('=== IntelHeader组件调试 ===\n');

// 检查IntelHeader.tsx
console.log('1. 检查IntelHeader.tsx:');
try {
    const content = fs.readFileSync(intelHeaderPath, 'utf8');
    const hasButtonRow = content.includes('collection-action-row');
    const hasAiScreener = content.includes('AI选股');
    const hasNavigateTo = content.includes('navigateTo');
    
    console.log(`   - 文件存在: ✅`);
    console.log(`   - 包含按钮行: ${hasButtonRow ? '✅' : '❌'}`);
    console.log(`   - 包含"AI选股": ${hasAiScreener ? '✅' : '❌'}`);
    console.log(`   - 导入navigateTo: ${hasNavigateTo ? '✅' : '❌'}`);
    
    if (hasButtonRow) {
        const buttonMatch = content.match(/collection-action-row[\s\S]*?<\/div>/);
        if (buttonMatch) {
            console.log('   - 按钮行内容:');
            const lines = buttonMatch[0].split('\n').slice(0, 6);
            lines.forEach(line => console.log('      ' + line.trim()));
            if (buttonMatch[0].split('\n').length > 6) {
                console.log('      ...');
            }
        }
    }
} catch (error) {
    console.log(`   - 文件读取错误: ${error.message}`);
}

console.log('\n2. 检查IntelPage.tsx:');
try {
    const content = fs.readFileSync(intelPagePath, 'utf8');
    const importsIntelHeader = content.includes('import { IntelHeader }');
    const usesIntelHeader = content.includes('<IntelHeader');
    
    console.log(`   - 导入IntelHeader: ${importsIntelHeader ? '✅' : '❌'}`);
    console.log(`   - 使用IntelHeader: ${usesIntelHeader ? '✅' : '❌'}`);
} catch (error) {
    console.log(`   - 文件读取错误: ${error.message}`);
}

console.log('\n3. 检查App.tsx:');
try {
    const content = fs.readFileSync(appPath, 'utf8');
    const importsIntelPage = content.includes('import { IntelPage }');
    const returnsIntelPage = content.includes('return <IntelPage />');
    
    console.log(`   - 导入IntelPage: ${importsIntelPage ? '✅' : '❌'}`);
    console.log(`   - 返回IntelPage: ${returnsIntelPage ? '✅' : '❌'}`);
    
    if (returnsIntelPage) {
        const lines = content.split('\n');
        const lineIndex = lines.findIndex(line => line.includes('return <IntelPage />'));
        if (lineIndex !== -1) {
            console.log(`   - 在第 ${lineIndex + 1} 行返回IntelPage`);
        }
    }
} catch (error) {
    console.log(`   - 文件读取错误: ${error.message}`);
}

console.log('\n4. 检查开发服务器:');
try {
    const response5173 = await fetch('http://localhost:5173');
    const response5174 = await fetch('http://localhost:5174');
    
    console.log(`   - 端口 5173: ${response5173.ok ? '✅ 运行中' : '❌ 未运行'}`);
    console.log(`   - 端口 5174: ${response5174.ok ? '✅ 运行中' : '❌ 未运行'}`);
} catch (error) {
    console.log(`   - 网络检查错误: ${error.message}`);
}

console.log('\n=== 调试完成 ===');
console.log('\n建议操作:');
console.log('1. 访问 http://localhost:5174 (新端口，无缓存)');
console.log('2. 按 Ctrl+Shift+R 强制刷新');
console.log('3. 检查浏览器控制台错误');
console.log('4. 如果新端口显示更新，说明代码正确，问题是缓存');
