import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue') },
  { path: '/register', component: () => import('../views/RegisterView.vue') },
  { path: '/', redirect: '/courses' },
  {
    path: '/courses',
    component: () => import('../views/CoursesView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/courses/:id',
    component: () => import('../views/CourseDetailView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/courses/:id/chat',
    component: () => import('../views/ChatView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/plans',
    component: () => import('../views/PlansView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/tasks',
    component: () => import('../views/TasksView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/profile',
    component: () => import('../views/ProfileView.vue'),
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) return '/login'
  if ((to.path === '/login' || to.path === '/register') && token) return '/courses'
  return true
})

export default router
