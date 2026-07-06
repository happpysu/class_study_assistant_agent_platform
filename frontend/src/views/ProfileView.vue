<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  listAllConversations,
  listCourses,
  listPlans,
  listTasks,
  updateMe,
} from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const stats = reactive({ courses: 0, plans: 0, tasksTodo: 0, conversations: 0 })
const conversations = ref([])
const courses = ref([])
const profileForm = reactive({ nickname: '', password: '' })
const saving = ref(false)

onMounted(async () => {
  await auth.fetchMe()
  profileForm.nickname = auth.user?.nickname || ''
  const [c, p, t, conv] = await Promise.all([
    listCourses(),
    listPlans(),
    listTasks({ completed: false }),
    listAllConversations(),
  ])
  courses.value = c.data
  stats.courses = c.data.length
  stats.plans = p.data.length
  stats.tasksTodo = t.data.length
  stats.conversations = conv.data.length
  conversations.value = conv.data.slice(0, 10)
})

async function saveProfile() {
  const payload = {}
  if (profileForm.nickname !== auth.user?.nickname) payload.nickname = profileForm.nickname
  if (profileForm.password) payload.password = profileForm.password
  if (!Object.keys(payload).length) {
    ElMessage.info('没有需要保存的修改')
    return
  }
  saving.value = true
  try {
    await updateMe(payload)
    await auth.fetchMe()
    profileForm.password = ''
    ElMessage.success('已保存')
  } finally {
    saving.value = false
  }
}

const courseName = (id) => courses.value.find((c) => c.id === id)?.name || '未知课程'
</script>

<template>
  <div>
    <h3>个人中心</h3>
    <el-row :gutter="16">
      <el-col :span="6">
        <el-card class="stat" @click="router.push('/courses')">
          <div class="stat-num">{{ stats.courses }}</div>
          <div class="stat-label">我的课程</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat" @click="router.push('/plans')">
          <div class="stat-num">{{ stats.plans }}</div>
          <div class="stat-label">学习计划</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat" @click="router.push('/tasks')">
          <div class="stat-num">{{ stats.tasksTodo }}</div>
          <div class="stat-label">未完成任务</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat">
          <div class="stat-num">{{ stats.conversations }}</div>
          <div class="stat-label">对话记录</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="block">
      <el-col :span="12">
        <el-card>
          <template #header>账号信息</template>
          <el-form label-width="80px">
            <el-form-item label="用户名">
              <el-input :model-value="auth.user?.username" disabled />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input :model-value="auth.user?.email" disabled />
            </el-form-item>
            <el-form-item label="昵称">
              <el-input v-model="profileForm.nickname" maxlength="64" />
            </el-form-item>
            <el-form-item label="新密码">
              <el-input
                v-model="profileForm.password"
                type="password"
                show-password
                placeholder="不修改请留空（至少 6 位）"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="saveProfile">保存修改</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>最近对话</template>
          <el-empty v-if="!conversations.length" description="暂无对话记录" :image-size="60" />
          <div
            v-for="conv in conversations"
            :key="conv.id"
            class="conv-row"
            @click="router.push(`/courses/${conv.course_id}/chat`)"
          >
            <el-icon><ChatDotRound /></el-icon>
            <span class="conv-title">{{ conv.title }}</span>
            <el-tag size="small">{{ courseName(conv.course_id) }}</el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.stat {
  text-align: center;
  cursor: pointer;
}
.stat-num {
  font-size: 28px;
  font-weight: 700;
  color: #409eff;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}
.block {
  margin-top: 16px;
}
.conv-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  cursor: pointer;
  border-bottom: 1px solid #f0f2f5;
  font-size: 13px;
  color: #606266;
}
.conv-row:hover {
  background: #f5f7fa;
}
.conv-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
