#!/usr/bin/env node

/**
 * 代码分割性能测试脚本
 * 测试路由级代码分割的效果
 */

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 配置
const CONFIG = {
  projectRoot: path.join(__dirname, '..'),
  buildOutputDir: 'dist',
  testRoutes: [
    '/',                    // 首页
    '/themes/test',         // 主题页面
    '/stocks/000001',       // 股票页面
    '/screener',            // 筛选器页面
    '/collection',          // 收集页面
    '/recap',               // 回顾页面
  ],
  metrics: {
    initialLoad: '首次加载时间',
    chunkSize: '代码块大小',
    chunkCount: '代码块数量',
    loadTime: '路由加载时间',
  },
};

class CodeSplittingTester {
  constructor() {
    this.results = [];
    this.buildStats = null;
  }

  /**
   * 运行构建并收集统计信息
   */
  runBuild() {
    console.log('🚀 开始构建项目...');

    try {
      // 清理之前的构建
      const distPath = path.join(CONFIG.projectRoot, CONFIG.buildOutputDir);
      if (fs.existsSync(distPath)) {
        fs.rmSync(distPath, { recursive: true });
        console.log('🧹 清理旧构建文件');
      }

      // 运行构建
      execSync('npm run build', {
        cwd: CONFIG.projectRoot,
        stdio: 'inherit',
      });

      console.log('✅ 构建完成');
      return true;
    } catch (error) {
      console.error('❌ 构建失败:', error.message);
      return false;
    }
  }

  /**
   * 分析构建输出
   */
  analyzeBuild() {
    console.log('📊 分析构建输出...');

    const distPath = path.join(CONFIG.projectRoot, CONFIG.buildOutputDir);
    const assetsPath = path.join(distPath, 'assets');

    if (!fs.existsSync(assetsPath)) {
      console.error('❌ 找不到构建输出目录');
      return null;
    }

    // 获取所有JS文件
    const jsFiles = fs.readdirSync(assetsPath)
      .filter(file => file.endsWith('.js'))
      .map(file => {
        const filePath = path.join(assetsPath, file);
        const stats = fs.statSync(filePath);
        return {
          name: file,
          size: stats.size,
          sizeKB: (stats.size / 1024).toFixed(2),
          path: filePath,
        };
      });

    // 按类型分组
    const chunks = {
      vendor: jsFiles.filter(f => f.name.includes('vendor')),
      chunk: jsFiles.filter(f => f.name.includes('chunk')),
      entry: jsFiles.filter(f => f.name.includes('index') || f.name.includes('main')),
      other: jsFiles.filter(f => !f.name.includes('vendor') && !f.name.includes('chunk') && !f.name.includes('index') && !f.name.includes('main')),
    };

    // 计算统计信息
    const totalSize = jsFiles.reduce((sum, file) => sum + file.size, 0);
    const vendorSize = chunks.vendor.reduce((sum, file) => sum + file.size, 0);
    const chunkSize = chunks.chunk.reduce((sum, file) => sum + file.size, 0);

    const stats = {
      totalFiles: jsFiles.length,
      totalSizeKB: (totalSize / 1024).toFixed(2),
      vendorFiles: chunks.vendor.length,
      vendorSizeKB: (vendorSize / 1024).toFixed(2),
      chunkFiles: chunks.chunk.length,
      chunkSizeKB: (chunkSize / 1024).toFixed(2),
      chunks: chunks,
      files: jsFiles,
    };

    console.log('📈 构建统计:');
    console.log(`   总文件数: ${stats.totalFiles}`);
    console.log(`   总大小: ${stats.totalSizeKB} KB`);
    console.log(`   Vendor文件: ${stats.vendorFiles} (${stats.vendorSizeKB} KB)`);
    console.log(`   代码块文件: ${stats.chunkFiles} (${stats.chunkSizeKB} KB)`);

    // 显示代码块详情
    console.log('\n🧩 代码块详情:');
    chunks.chunk.forEach(chunk => {
      console.log(`   ${chunk.name}: ${chunk.sizeKB} KB`);
    });

    this.buildStats = stats;
    return stats;
  }

  /**
   * 模拟路由加载测试
   */
  simulateRouteLoading() {
    console.log('\n🧪 模拟路由加载测试...');

    if (!this.buildStats) {
      console.error('❌ 请先运行构建分析');
      return;
    }

    const routeTests = [];

    // 模拟不同路由的加载
    CONFIG.testRoutes.forEach(route => {
      // 估算加载时间（基于文件大小和网络速度）
      const estimatedLoadTime = this.estimateLoadTime(route);

      // 确定需要加载的代码块
      const requiredChunks = this.getRequiredChunksForRoute(route);

      routeTests.push({
        route,
        estimatedLoadTime,
        requiredChunks: requiredChunks.length,
        chunkNames: requiredChunks.map(c => c.name),
        totalSizeKB: requiredChunks.reduce((sum, c) => sum + parseFloat(c.sizeKB), 0).toFixed(2),
      });
    });

    // 显示结果
    console.log('📊 路由加载模拟结果:');
    routeTests.forEach(test => {
      console.log(`\n   ${test.route}:`);
      console.log(`     预估加载时间: ${test.estimatedLoadTime}ms`);
      console.log(`     需要代码块: ${test.requiredChunks}个`);
      console.log(`     总大小: ${test.totalSizeKB} KB`);
      if (test.chunkNames.length > 0) {
        console.log(`     代码块: ${test.chunkNames.join(', ')}`);
      }
    });

    this.routeTests = routeTests;
    return routeTests;
  }

  /**
   * 估算路由加载时间
   */
  estimateLoadTime(route) {
    if (!this.buildStats) return 0;

    // 基础加载时间（vendor + 公共代码）
    const baseChunks = [
      ...this.buildStats.chunks.vendor,
      ...this.buildStats.chunks.entry.filter(f => f.name.includes('index')),
    ];

    const baseSize = baseChunks.reduce((sum, c) => sum + c.size, 0);

    // 路由特定代码块
    const routeChunks = this.getRequiredChunksForRoute(route);
    const routeSize = routeChunks.reduce((sum, c) => sum + c.size, 0);

    // 总大小（字节）
    const totalSize = baseSize + routeSize;

    // 模拟加载时间（假设网络速度：1MB/s）
    const networkSpeed = 1024 * 1024; // 1 MB/s
    const loadTime = (totalSize / networkSpeed) * 1000; // 毫秒

    // 添加解析和执行时间
    const parseExecuteTime = 100 + (routeChunks.length * 50);

    return Math.round(loadTime + parseExecuteTime);
  }

  /**
   * 获取路由需要的代码块
   */
  getRequiredChunksForRoute(route) {
    if (!this.buildStats) return [];

    const chunks = [];

    // 根据路由确定需要的代码块
    if (route === '/' || route.startsWith('/themes/')) {
      chunks.push(...this.buildStats.chunks.chunk.filter(c => c.name.includes('chunk-intel') || c.name.includes('chunk-theme')));
    } else if (route.startsWith('/stocks/')) {
      chunks.push(...this.buildStats.chunks.chunk.filter(c => c.name.includes('chunk-stock')));
    } else if (route.startsWith('/screener')) {
      chunks.push(...this.buildStats.chunks.chunk.filter(c => c.name.includes('chunk-screener')));
    } else if (route.startsWith('/collection')) {
      chunks.push(...this.buildStats.chunks.chunk.filter(c => c.name.includes('chunk-collection')));
    } else if (route.startsWith('/recap')) {
      chunks.push(...this.buildStats.chunks.chunk.filter(c => c.name.includes('chunk-recap')));
    }

    return chunks;
  }

  /**
   * 生成优化建议
   */
  generateRecommendations() {
    console.log('\n💡 优化建议:');

    const recommendations = [];

    if (!this.buildStats) {
      recommendations.push('请先完成构建分析');
      return recommendations;
    }

    // 检查vendor包大小
    const vendorSizeKB = parseFloat(this.buildStats.vendorSizeKB);
    if (vendorSizeKB > 500) {
      recommendations.push({
        type: 'warning',
        title: 'Vendor包过大',
        message: `Vendor包大小 ${vendorSizeKB}KB，考虑进一步拆分`,
        action: '检查是否有不必要的依赖或使用动态导入',
      });
    }

    // 检查代码块数量
    if (this.buildStats.chunkFiles > 10) {
      recommendations.push({
        type: 'info',
        title: '代码块数量较多',
        message: `共有 ${this.buildStats.chunkFiles} 个代码块`,
        action: '考虑合并相关路由的代码块',
      });
    }

    // 检查大文件
    const largeFiles = this.buildStats.files.filter(f => parseFloat(f.sizeKB) > 100);
    if (largeFiles.length > 0) {
      recommendations.push({
        type: 'warning',
        title: '发现大文件',
        message: `${largeFiles.length} 个文件超过100KB`,
        action: '优化这些文件的代码或进一步拆分',
        files: largeFiles.map(f => `${f.name} (${f.sizeKB}KB)`),
      });
    }

    // 显示建议
    recommendations.forEach((rec, index) => {
      console.log(`\n   ${index + 1}. ${rec.title}:`);
      console.log(`     问题: ${rec.message}`);
      console.log(`     建议: ${rec.action}`);
      if (rec.files) {
        console.log(`     相关文件: ${rec.files.join(', ')}`);
      }
    });

    return recommendations;
  }

  /**
   * 运行完整测试
   */
  runFullTest() {
    console.log('🔍 代码分割性能测试');
    console.log('=' .repeat(60));

    // 1. 运行构建
    const buildSuccess = this.runBuild();
    if (!buildSuccess) {
      console.error('❌ 构建失败，测试中止');
      return;
    }

    // 2. 分析构建输出
    const buildStats = this.analyzeBuild();
    if (!buildStats) {
      console.error('❌ 构建分析失败');
      return;
    }

    // 3. 模拟路由加载
    const routeTests = this.simulateRouteLoading();

    // 4. 生成建议
    const recommendations = this.generateRecommendations();

    // 5. 生成报告
    const report = {
      timestamp: new Date().toISOString(),
      buildStats,
      routeTests,
      recommendations,
      summary: {
        totalSizeKB: buildStats.totalSizeKB,
        chunkCount: buildStats.chunkFiles,
        estimatedImprovement: this.calculateImprovement(),
      },
    };

    // 保存报告
    this.saveReport(report);

    console.log('\n✅ 测试完成');
    return report;
  }

  /**
   * 计算优化效果
   */
  calculateImprovement() {
    if (!this.buildStats || !this.routeTests) return 'N/A';

    // 假设未使用代码分割的情况（所有代码在一个bundle中）
    const monolithicSize = parseFloat(this.buildStats.totalSizeKB);

    // 平均路由加载大小
    const avgRouteSize = this.routeTests.reduce((sum, test) =>
      sum + parseFloat(test.totalSizeKB), 0) / this.routeTests.length;

    // vendor大小（需要首次加载）
    const vendorSize = parseFloat(this.buildStats.vendorSizeKB);

    // 优化后的平均加载大小
    const optimizedSize = vendorSize + avgRouteSize;

    // 计算改进百分比
    const improvement = ((monolithicSize - optimizedSize) / monolithicSize * 100).toFixed(1);

    return `${improvement}%`;
  }

  /**
   * 保存测试报告
   */
  saveReport(report) {
    const reportDir = path.join(CONFIG.projectRoot, 'reports');
    if (!fs.existsSync(reportDir)) {
      fs.mkdirSync(reportDir, { recursive: true });
    }

    const reportFile = path.join(reportDir, `code-splitting-report-${Date.now()}.json`);

    fs.writeFileSync(
      reportFile,
      JSON.stringify(report, null, 2),
      'utf8'
    );

    console.log(`📄 测试报告已保存: ${reportFile}`);
  }
}

// 运行测试
const tester = new CodeSplittingTester();
tester.runFullTest();

export default CodeSplittingTester;