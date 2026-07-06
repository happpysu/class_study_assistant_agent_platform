<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createMultiPlan, createPlan, deletePlan, listCourses, listPlans } from '../api'

const plans = ref([])
const courses = ref([])
const creating = ref(false)
const multiVisible = ref(false)

const form = reactive({ course_id: null, goal: '', deadline: '', daily_hours: 2 })
const multiForm = reactive({
  daily_hours: 3,
  course_goals: [{ course_id: null, goal: '', deadline: '' }],
})

async function refresh() {
  const [{ data: planData }, { data: courseData }] = await Promise.all([
    listPlans(),
    listCourses(),
  ])
  plans.value = planData
  courses.value = courseData
}
onMounted(refresh)

async function submitPlan() {
  if (!form.goal.trim() || !form.deadline) {
    ElMessage.warning('请填写学习目标和截止日期')
    return
  }
  creating.value = true
  try {
    const { data } = await createPlan({ ...form, course_id: form.course_id || null })
    notifyCreated(data)
    form.goal = ''
    await refresh()
  } finally {
    creating.value = false
  }
}

function addGoalRow() {
  multiForm.course_goals.push({ course_id: null, goal: '', deadline: '' })
}

async function submitMultiPlan() {
  const goals = multiForm.course_goals.filter(
    (g) => g.course_id && g.goal.trim() && g.deadline,
  )
  if (!goals.length) {
    ElMessage.warning('请至少完整填写一门课程的目标')
    return
  }
  creating.value = true
  try {
    const { data } = await createMultiPlan({
      daily_hours: multiForm.daily_hours,
      course_goals: goals,
    })
    multiVisible.value = false
    notifyCreated(data)
    await refresh()
  } finally {
    creating.value = false
  }
}

function notifyCreated(plan) {
  const suffix =
    plan.agent_mode === 'fallback'
      ? '（离线模式：均匀拆分。配置 API Key 后可获得智能计划）'
      : ''
  ElMessage.success(`计划已生成，每日待办已加入任务列表${suffix}`)
}

async function removePlan(plan) {
  await ElMessageBox.confirm('删除该计划？（已生成的待办任务会保留）', '删除确认', {
    type: 'warning',
  })
  await deletePlan(plan.id)
  await refresh()
}

const courseName = (id) => courses.value.find((c) => c.id === id)?.name || ''
</script>

<template>
  <div>
    <div class="toolbar">
      <h3>学习计划</h3>
      <el-button @click="multiVisible = true">
        <el-icon><Files /></el-icon>多课程综合规划
      </el-button>
    </div>

    <el-card class="block">
      <template #header>生成学习计划（自动拆解为阶段任务与每日待办）</template>
      <el-form inline>
        <el-form-item label="课程">
          <el-select v-model="form.course_id" clearable placeholder="不限定课程" style="width: 160px">
            <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="学习目标">
          <el-input
            v-model="form.goal"
            placeholder="如：两周复习完高等数学期末考试"
            style="width: 280px"
          />
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker v-model="form.deadline" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="每日可用">
          <el-input-number v-model="form.daily_hours" :min="0.5" :max="24" :step="0.5" />
          <span class="unit">小时</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="creating" @click="submitPlan">生成计划</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-empty v-if="!plans.length" description="还没有学习计划" />
    <el-card v-for="plan in plans" :key="plan.id" class="block">
      <template #header>
        <div class="plan-header">
          <div>
            <el-tag v-if="plan.plan_type === 'multi'" type="success" size="small">多课程</el-tag>
            <el-tag v-else-if="plan.course_id" size="small">{{ courseName(plan.course_id) }}</el-tag>
            <span class="plan-goal">{{ plan.goal }}</span>
          </div>
          <div class="plan-meta">
            <span>截止 {{ plan.deadline }} · 每日 {{ plan.daily_hours }}h</span>
            <el-button size="small" link type="danger" @click="removePlan(plan)">删除</el-button>
          </div>
        </div>
      </template>
      <p v-if="plan.content.overview" class="overview">{{ plan.content.overview }}</p>
      <el-collapse>
        <el-collapse-item v-if="plan.content.stages?.length" title="阶段任务">
          <el-table :data="plan.content.stages" size="small">
            <el-table-column prop="name" label="阶段" width="140" />
            <el-table-column label="时间" width="200">
              <template #default="{ row }">{{ row.start_date }} ~ {{ row.end_date }}</template>
            </el-table-column>
            <el-table-column prop="goal" label="阶段目标" />
          </el-table>
        </el-collapse-item>
        <el-collapse-item
          v-if="plan.content.daily_tasks?.length"
          :title="`每日待办（${plan.content.daily_tasks.length} 项，已同步到任务列表）`"
        >
          <el-table :data="plan.content.daily_tasks" size="small" max-height="320">
            <el-table-column prop="date" label="日期" width="110" />
            <el-table-column prop="course" label="课程" width="120" />
            <el-table-column prop="title" label="任务" min-width="160" />
            <el-table-column prop="detail" label="说明" min-width="160" show-overflow-tooltip />
            <el-table-column prop="hours" label="时长(h)" width="80" />
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <el-dialog v-model="multiVisible" title="多课程综合规划" width="640px">
      <el-alert
        :closable="false"
        class="block"
        title="按各课程截止时间与任务量，生成统一的每日学习安排"
        type="info"
      />
      <div v-for="(g, i) in multiForm.course_goals" :key="i" class="goal-row">
        <el-select v-model="g.course_id" placeholder="选择课程" style="width: 150px">
          <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-input v-model="g.goal" placeholder="该课程的目标" style="width: 220px" />
        <el-date-picker v-model="g.deadline" type="date" value-format="YYYY-MM-DD" placeholder="截止日期" style="width: 150px" />
      </div>
      <el-button link type="primary" @click="addGoalRow">+ 添加课程</el-button>
      <el-form-item label="每日总可用时间" class="block" label-width="120px">
        <el-input-number v-model="multiForm.daily_hours" :min="1" :max="24" :step="0.5" />
        <span class="unit">小时</span>
      </el-form-item>
      <template #footer>
        <el-button @click="multiVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitMultiPlan">生成综合计划</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.block {
  margin-bottom: 16px;
}
.unit {
  margin-left: 6px;
  color: #909399;
}
.plan-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.plan-goal {
  margin-left: 8px;
  font-weight: 600;
}
.plan-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: #909399;
  flex-shrink: 0;
}
.overview {
  font-size: 13px;
  color: #606266;
  margin: 0 0 12px;
}
.goal-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
</style>
