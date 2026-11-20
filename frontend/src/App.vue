<template>
  <router-view />
</template>

<style>
:root {
  /* ===== 品牌色：珊瑚红 → 暖橙，年轻化但不脱离电商心智 ===== */
  --brand: #ff4d4f;
  --brand-strong: #e8362f;
  --brand-soft: #fff1ed;
  --brand-gradient: linear-gradient(135deg, #ff5f57 0%, #ff8a3d 100%);
  --ink: #17181c;
  --muted: #8a8f99;
  --bg: #f7f5f2;
  --surface: rgba(255, 255, 255, .88);
  --line: rgba(23, 24, 28, .08);
  --shadow-sm: 0 6px 20px rgba(48, 28, 16, .06);
  --shadow-md: 0 18px 50px rgba(48, 28, 16, .12);
  --radius-lg: 24px;
  --radius-md: 16px;

  /* 覆盖 Element Plus 主色与圆角 */
  --el-color-primary: #ff4d4f;
  --el-color-primary-light-3: #ff7d76;
  --el-color-primary-light-5: #ffa39e;
  --el-color-primary-light-7: #ffccc7;
  --el-color-primary-light-8: #ffe0dc;
  --el-color-primary-light-9: #fff1f0;
  --el-color-primary-dark-2: #d9363e;
  --el-border-radius-base: 12px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

html { scroll-behavior: smooth; }

body {
  min-height: 100vh;
  font-family: "Inter", "HarmonyOS Sans SC", "PingFang SC", "Microsoft YaHei",
    system-ui, -apple-system, sans-serif;
  color: var(--ink);
  background:
    radial-gradient(900px 520px at 6% -12%, rgba(255, 122, 89, .16), transparent 62%),
    radial-gradient(820px 500px at 100% -4%, rgba(255, 183, 3, .13), transparent 58%),
    var(--bg);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

a { text-decoration: none; color: inherit; }

::selection { background: rgba(255, 77, 79, .18); }

/* 细滚动条，避免老式浏览器默认样式 */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: rgba(23, 24, 28, .16); border-radius: 999px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(23, 24, 28, .28); }

.price {
  color: var(--brand);
  font-weight: 700;
  letter-spacing: -.02em;
}

/* ===== Element Plus 全局年轻化 ===== */
.el-button {
  border-radius: 999px;
  font-weight: 600;
  transition: transform .2s ease, box-shadow .2s ease, filter .2s ease;
}
.el-button--primary {
  background: var(--brand-gradient);
  border-color: transparent;
  box-shadow: 0 8px 20px rgba(255, 95, 87, .22);
}
.el-button--primary:hover {
  transform: translateY(-1px);
  filter: brightness(1.04);
  box-shadow: 0 12px 26px rgba(255, 95, 87, .28);
}
.el-input__wrapper,
.el-textarea__inner {
  border-radius: 14px;
  box-shadow: 0 0 0 1px var(--line) inset;
  background: rgba(255, 255, 255, .92);
  transition: box-shadow .2s ease;
}
.el-input__wrapper.is-focus {
  box-shadow: 0 0 0 2px rgba(255, 77, 79, .22) inset;
}
.el-card,
.el-dialog,
.el-drawer,
.el-message-box {
  border-radius: var(--radius-lg);
  border: none;
  box-shadow: var(--shadow-sm);
}
.el-tag { border-radius: 999px; }
.el-table { border-radius: var(--radius-md); overflow: hidden; }
.el-empty { padding: 40px 0; }
</style>
