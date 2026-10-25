import { createRouter, createWebHistory } from 'vue-router'
import { TOKEN_KEY, isMerchant } from '../api'

import MallLayout from '../components/MallLayout.vue'
import AdminLayout from '../views/admin/AdminLayout.vue'

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
      { path: 'reviews', name: 'admin-reviews', component: () => import('../views/admin/AdminReviews.vue'), meta: { title: '评价管理' } },
      { path: 'documents', name: 'admin-documents', component: () => import('../views/admin/AdminDocuments.vue'), meta: { title: '知识库管理' } },
      { path: 'categories', name: 'admin-categories', component: () => import('../views/admin/AdminCategories.vue'), meta: { title: '知识分类' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 登录守卫：需要登录/商家身份的页面，不满足则跳登录页
router.beforeEach((to) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (to.meta.requiresAuth && !token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.matched.some((r) => r.meta.requiresMerchant) && !isMerchant()) {
    return '/'
  }
  if (to.path === '/login' && token) {
    return '/'
  }
  return true
})

router.afterEach((to) => {
  if (to.meta.title) document.title = `${to.meta.title} - 智购商城`
})

export default router
