console.log("AI_THEME_APP_ROOT:", process.env.AI_THEME_APP_ROOT);
console.log("PROJECT_ROOT:", process.env.PROJECT_ROOT);
console.log("cwd:", process.cwd());
console.log("所有环境变量包含AI_THEME_APP_ROOT:", Object.keys(process.env).filter(k => k.includes('AI_THEME') || k.includes('PROJECT')));
