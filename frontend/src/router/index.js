import { createRouter, createWebHistory } from 'vue-router'
import { TOKEN_KEY, isMerchant, isPlatformAdmin } from '../api'

import MallLayout from '../components/MallLayout.vue'
import AdminLayout from '../views/admin/AdminLayout.vue'
import PlatformLayout from '../views/platform/PlatformLayout.vue'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
  {
    path: '/',
    component: MallLayout,
    children: [
      { path: '', name: 'home', component: () => import('../views/HomeView.vue'), meta: { title: '首页' } },
      { path: 'search', name: 'search', component: () => import('../views/SearchView.vue'), meta: { title: '商品搜索' } },
      { path: 'product/:id', name: 'product', component: () => import('../views/ProductDetailView.vue'), meta: { title: '商品详情' } },
      { path: 'cart', name: 'cart', component: () => import('../views/CartView.vue'), meta: { title: '购物车', requiresAuth: true } },
      { path: 'checkout', name: 'checkout', component: () => import('../views/CheckoutView.vue'), meta: { title: '确认订单', requiresAuth: true } },
      { path: 'orders', name: 'orders', component: () => import('../views/OrdersView.vue'), meta: { title: '我的订单', requiresAuth: true } },
      { path: 'addresses', name: 'addresses', component: () => import('../views/AddressView.vue'), meta: { title: '地址管理', requiresAuth: true } },
    ],
  },
  {
    path: '/admin',
    component: AdminLayout,
    meta: { requiresAuth: true, requiresMerchant: true },
    children: [
      { path: '', redirect: '/admin/products' },
      { path: 'products', name: 'admin-products', component: () => import('../views/admin/AdminProducts.vue'), meta: { title: '商品管理' } },
      { path: 'orders', name: 'admin-orders', component: () => import('../views/admin/AdminOrders.vue'), meta: { title: '订单管理' } },
      { path: 'aftersale', name: 'admin-aftersale', component: () => import('../views/admin/AdminAfterSales.vue'), meta: { title: '售后处理' } },
      { path: 'reviews', name: 'admin-reviews', component: () => import('../views/admin/AdminReviews.vue'), meta: { title: '评价管理' } },
    ],
  },
  {
    path: '/platform',
    component: PlatformLayout,
    meta: { requiresAuth: true, requiresPlatform: true },
    children: [
      { path: '', redirect: '/platform/dashboard' },
      { path: 'dashboard', name: 'platform-dashboard', component: () => import('../views/platform/PlatformDashboard.vue'), meta: { title: '平台概览' } },
      { path: 'insights', name: 'platform-insights', component: () => import('../views/platform/PlatformInsights.vue'), meta: { title: '智能洞察' } },
      { path: 'tenants', name: 'platform-tenants', component: () => import('../views/platform/PlatformTenants.vue'), meta: { title: '商家管理' } },
      { path: 'categories', name: 'platform-categories', component: () => import('../views/platform/PlatformCategories.vue'), meta: { title: '平台分类' } },
      { path: 'products', name: 'platform-products', component: () => import('../views/platform/PlatformProducts.vue'), meta: { title: '商品监管' } },
      { path: 'orders', name: 'platform-orders', component: () => import('../views/platform/PlatformOrders.vue'), meta: { title: '订单监管' } },
      { path: 'customers', name: 'platform-customers', component: () => import('../views/platform/PlatformCustomers.vue'), meta: { title: '用户管理' } },
      { path: 'knowledge', name: 'platform-knowledge', component: () => import('../views/platform/PlatformKnowledge.vue'), meta: { title: '知识库管理' } },
      { path: 'knowledge-categories', name: 'platform-knowledge-categories', component: () => import('../views/platform/PlatformKnowledgeCategories.vue'), meta: { title: '知识分类' } },
      { path: 'feedback', name: 'platform-feedback', component: () => import('../views/platform/PlatformFeedback.vue'), meta: { title: '反馈分析' } },
      { path: 'audit', name: 'platform-audit', component: () => import('../views/platform/PlatformAudit.vue'), meta: { title: '操作审计' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 登录守卫：需要登录/商家身份的页面，不满足则跳登录页
// 设计要点（面试考点）：
// - 权限声明在路由 meta 上（requiresAuth / requiresMerchant），守卫统一拦截，
//   页面组件内零权限代码 —— 与后端 require_permission 依赖注入是同一思想：
//   权限与业务解耦，声明在"入口签名"上；
// - 被拦截时带 redirect 参数，登录成功后原路跳回，不丢用户上下文。
router.beforeEach((to) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (to.meta.requiresAuth && !token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.matched.some((r) => r.meta.requiresMerchant) && !isMerchant()) {
    return isPlatformAdmin() ? '/platform/dashboard' : '/'
  }
  if (to.matched.some((r) => r.meta.requiresPlatform) && !isPlatformAdmin()) {
    return isMerchant() ? '/admin/products' : '/'
  }
  if (to.path === '/login' && token) {
    if (isPlatformAdmin()) return '/platform/dashboard'
    return isMerchant() ? '/admin/products' : '/'
  }
  return true
})

router.afterEach((to) => {
  if (to.meta.title) document.title = `${to.meta.title} - 智购商城`
})

export default router
