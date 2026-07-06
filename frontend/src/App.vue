<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const showLayout = computed(() => route.meta.requiresAuth)
const activeMenu = computed(() => {
  if (route.path.startsWith('/courses')) return '/courses'
  return route.path
})

onMounted(() => auth.fetchMe())

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-container v-if="showLayout" class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">📚 课程学习助手</div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item index="/courses">
          <el-icon><Collection /></el-icon>我的课程
        </el-menu-item>
        <el-menu-item index="/plans">
          <el-icon><Calendar /></el-icon>学习计划
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><List /></el-icon>待办任务
        </el-menu-item>
        <el-menu-item index="/profile">
          <el-icon><User /></el-icon>个人中心
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span />
        <el-dropdown @command="handleLogout">
          <span class="user-chip">
            <el-icon><UserFilled /></el-icon>
            {{ auth.user?.nickname || auth.user?.username || '同学' }}
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
  <router-view v-else />
</template>

<style>
body {
  margin: 0;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: #f5f7fa;
}
.layout {
  height: 100vh;
}
.aside {
  background: #fff;
  border-right: 1px solid #e4e7ed;
}
.logo {
  padding: 20px 16px;
  font-size: 16px;
  font-weight: 600;
}
.menu {
  border-right: none;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}
.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #303133;
}
.main {
  overflow-y: auto;
}
</style>
