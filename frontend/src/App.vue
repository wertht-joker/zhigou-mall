<template>
  <router-view />
</template>

<style>
:root {
  /* 京东红主题：覆盖 Element Plus 主色 */
  --el-color-primary: #e1251b;
  --el-color-primary-light-3: #ea5a4f;
  --el-color-primary-light-5: #f08f83;
  --el-color-primary-light-7: #f7c3ba;
  --el-color-primary-light-8: #fadbd2;
  --el-color-primary-light-9: #fcedea;
  --el-color-primary-dark-2: #b41e15;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, "Microsoft YaHei", "PingFang SC", sans-serif;
  background: #f4f5f7;
  color: #262626;
}
a { text-decoration: none; color: inherit; }
.price { color: #e1251b; font-weight: 600; }
</style>
