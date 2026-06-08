#!/usr/bin/env node

/**
 * npm postinstall 脚本
 * 自动将 stock-analyzer plugin 添加到 Claude Code
 */

const { execSync } = require("child_process");
const path = require("path");

const pluginDir = __dirname;

console.log("📦 正在安装 stock-analyzer skill 到 Claude Code...");

try {
  // 添加 marketplace
  console.log("  添加 marketplace...");
  execSync(`claude plugins marketplace add "${pluginDir}"`, {
    stdio: "inherit",
    timeout: 30000,
  });

  // 安装 plugin
  console.log("  安装 plugin...");
  execSync("claude plugins install stock-analyzer", {
    stdio: "inherit",
    timeout: 30000,
  });

  console.log("");
  console.log("✅ 安装完成！");
  console.log("");
  console.log("可用的 skills:");
  console.log("  /stock <代码>    - 单股分析");
  console.log("  /market          - 大盘复盘");
  console.log("  /sector <板块>   - 板块分析");
  console.log("  /screener        - 选股策略");
  console.log("  /technical <代码> - 技术分析");
  console.log("  /portfolio       - 持仓检查");
  console.log("  /financial-analyst - 财务分析");
  console.log("  /investment-researcher - 投资研究");
  console.log("");
  console.log("使用方式：直接在 Claude Code 中输入 /skill-name 参数");
  console.log("例如：/stock 贵州茅台 quick");
} catch (error) {
  console.error("");
  console.error("⚠️  自动安装失败，请手动执行以下命令：");
  console.error("");
  console.error(`  claude plugins marketplace add "${pluginDir}"`);
  console.error("  claude plugins install stock-analyzer");
  console.error("");
  console.error("错误信息：", error.message);
  // 不退出，让 npm install 继续
}
