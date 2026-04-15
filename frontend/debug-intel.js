// 调试脚本：检查IntelHeader组件
const fs = require('fs');
const path = require('path');

const intelHeaderPath = path.join(__dirname, 'src/components/intel/IntelHeader.tsx');
const intelPagePath = path.join(__dirname, 'src/routes/intel/IntelPage.tsx');
const appPath = path.join(__dirname, 'src/App.tsx');

console.log('=== IntelHeader组件调试 ===\n');

// 检查IntelHeader.tsx
console.log('1. 检查IntelHeader.tsx:');
if (fs.existsSync(intelHeaderPath)) {
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
            console.log(buttonMatch[0].split('\n').map(line => '      ' + line).join('\n').substring(0, 300) + '...');
        }
    }
} else {
    console.log('   - 文件不存在: ❌');
}

console.log('\n2. 检查IntelPage.tsx:');
if (fs.existsSync(intelPagePath)) {
    const content = fs.readFileSync(intelPagePath, 'utf8');
    const importsIntelHeader = content.includes('import { IntelHeader }');
    const usesIntelHeader = content.includes('<IntelHeader');
    
    console.log(`   - 导入IntelHeader: ${importsIntelHeader ? '✅' : '❌'}`);
    console.log(`   - 使用IntelHeader: ${usesIntelHeader ? '✅' : '❌'}`);
} else {
    console.log('   - 文件不存在: ❌');
}

console.log('\n3. 检查App.tsx:');
if (fs.existsSync(appPath)) {
    const content = fs.readFileSync(appPath, 'utf8');
    const importsIntelPage = content.includes('import { IntelPage }');
    const returnsIntelPage = content.includes('return <IntelPage />');
    
    console.log(`   - 导入IntelPage: ${importsIntelPage ? '✅' : '❌'}`);
    console.log(`   - 返回IntelPage: ${returnsIntelPage ? '✅' : '❌'}`);
    
    if (returnsIntelPage) {
        const match = content.match(/return <IntelPage \/>/);
        if (match) {
            const lineNum = content.substring(0, match.index).split('\n').length;
            console.log(`   - 在第 ${lineNum} 行返回IntelPage`);
        }
    }
} else {
    console.log('   - 文件不存在: ❌');
}

console.log('\n4. 检查构建状态:');
try {
    const buildOutput = fs.readdirSync(path.join(__dirname, 'dist/assets')).filter(f => f.endsWith('.js'));
    console.log(`   - 构建文件数量: ${buildOutput.length}`);
    
    if (buildOutput.length > 0) {
        const jsFile = path.join(__dirname, 'dist/assets', buildOutput[0]);
        const jsContent = fs.readFileSync(jsFile, 'utf8');
        const hasAiScreenerInBuild = jsContent.includes('AI选股');
        console.log(`   - 构建文件中包含"AI选股": ${hasAiScreenerInBuild ? '✅' : '❌'}`);
    }
} catch (error) {
    console.log(`   - 构建目录不存在或无法访问: ${error.message}`);
}

console.log('\n=== 调试完成 ===');
