<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createTask, deleteTask, listCourses, listTasks, updateTask } from '../api'

const allTasks = ref([])
const courses = ref([])
const viewMode = ref('list') // list / calendar
const filterStatus = ref('todo') // todo / done / all
const calendarDate = ref(new Date())
const form = reactive({ title: '', detail: '', course_id: null, due_date: '' })

const todayStr = () => new Date().toISOString().slice(0, 10)

async function refresh() {
  const [{ data: taskData }, { data: courseData }] = await Promise.all([
    listTasks(),
    listCourses(),
  ])
  allTasks.value = taskData
  courses.value = courseData
}
onMounted(refresh)

const filteredTasks = computed(() => {
  if (filterStatus.value === 'todo') return allTasks.value.filter((t) => !t.completed)
  if (filterStatus.value === 'done') return allTasks.value.filter((t) => t.completed)
  return allTasks.value
})

const reminders = computed(() => {
  const today = todayStr()
  const horizon = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10)
  const pending = allTasks.value.filter((t) => !t.completed && t.due_date)
  return {
    overdue: pending.filter((t) => t.due_date < today),
    today: pending.filter((t) => t.due_date === today),
    upcoming: pending.filter((t) => t.due_date > today && t.due_date <= horizon),
  }
})

const tasksOn = (day) => allTasks.value.filter((t) => t.due_date === day)

async function addTask() {
  if (!form.title.trim()) {
    ElMessage.warning('请填写任务内容')
    return
  }
  await createTask({
    title: form.title,
    detail: form.detail,
    course_id: form.course_id || null,
    due_date: form.due_date || null,
  })
  Object.assign(form, { title: '', detail: '', course_id: null, due_date: '' })
  await refresh()
}

async function toggle(task) {
  await updateTask(task.id, { completed: !task.completed })
  await refresh()
}

async function remove(task) {
  await ElMessageBox.confirm(`删除任务「${task.title}」？`, '删除确认', { type: 'warning' })
  await deleteTask(task.id)
  await refresh()
}

const courseName = (id) => courses.value.find((c) => c.id === id)?.name || ''
const isOverdue = (task) => !task.completed && task.due_date && task.due_date < todayStr()
</script>

<template>
  <div>
    <div class="toolbar">
      <h3>待办任务</h3>
      <div class="toolbar-right">
        <el-radio-group v-model="viewMode">
          <el-radio-button value="list">列表</el-radio-button>
          <el-radio-button value="calendar">日历</el-radio-button>
        </el-radio-group>
        <el-radio-group v-if="viewMode === 'list'" v-model="filterStatus">
          <el-radio-button value="todo">未完成</el-radio-button>
          <el-radio-button value="done">已完成</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <el-row :gutter="12" class="block">
      <el-col :span="8">
        <el-card class="remind-card overdue-card">
          <div class="remind-num">{{ reminders.overdue.length }}</div>
          <div class="remind-label">已逾期</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="remind-card today-card">
          <div class="remind-num">{{ reminders.today.length }}</div>
          <div class="remind-label">今天到期</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="remind-card upcoming-card">
          <div class="remind-num">{{ reminders.upcoming.length }}</div>
          <div class="remind-label">3 天内到期</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="block">
      <el-form inline>
        <el-form-item>
          <el-input v-model="form.title" placeholder="任务内容" style="width: 240px" @keyup.enter="addTask" />
        </el-form-item>
        <el-form-item>
          <el-select v-model="form.course_id" clearable placeholder="关联课程（选填）" style="width: 170px">
            <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-date-picker v-model="form.due_date" type="date" value-format="YYYY-MM-DD" placeholder="截止日期" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="addTask">添加任务</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 日历视图 -->
    <el-card v-if="viewMode === 'calendar'">
      <el-calendar v-model="calendarDate">
        <template #date-cell="{ data }">
          <div class="cal-cell">
            <span class="cal-day">{{ data.day.split('-')[2] }}</span>
            <div
              v-for="t in tasksOn(data.day)"
              :key="t.id"
              class="cal-task"
              :class="{ 'cal-done': t.completed, 'cal-overdue': isOverdue(t) }"
              :title="t.title"
              @click.stop="toggle(t)"
            >
              {{ t.title }}
            </div>
          </div>
        </template>
      </el-calendar>
      <div class="cal-legend">
        <span class="legend-item"><i class="dot dot-normal" />待办</span>
        <span class="legend-item"><i class="dot dot-overdue" />已逾期</span>
        <span class="legend-item"><i class="dot dot-done" />已完成</span>
        <span class="legend-tip">点击任务可切换完成状态</span>
      </div>
    </el-card>

    <!-- 列表视图 -->
    <el-card v-else>
      <template #header>
        任务列表<span class="count">（{{ reminders.overdue.length + reminders.today.length }} 项急需处理）</span>
      </template>
      <el-empty v-if="!filteredTasks.length" description="暂无任务" />
      <div v-for="task in filteredTasks" :key="task.id" class="task-row" :class="{ done: task.completed }">
        <el-checkbox :model-value="task.completed" @change="toggle(task)" />
        <div class="task-main">
          <div class="task-title">{{ task.title }}</div>
          <div class="task-meta">
            <el-tag v-if="task.course_id" size="small">{{ courseName(task.course_id) }}</el-tag>
            <el-tag v-if="task.plan_id" size="small" type="success">来自学习计划</el-tag>
            <span v-if="task.due_date" :class="{ overdue: isOverdue(task) }">
              {{ isOverdue(task) ? '已逾期 ' : '截止 ' }}{{ task.due_date }}
            </span>
            <span v-if="task.detail" class="detail">{{ task.detail }}</span>
          </div>
        </div>
        <el-button link type="danger" size="small" @click="remove(task)">删除</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar-right {
  display: flex;
  gap: 12px;
}
.block {
  margin-bottom: 16px;
}
.remind-card {
  text-align: center;
}
.remind-num {
  font-size: 26px;
  font-weight: 700;
}
.overdue-card .remind-num {
  color: #f56c6c;
}
.today-card .remind-num {
  color: #e6a23c;
}
.upcoming-card .remind-num {
  color: #409eff;
}
.remind-label {
  font-size: 13px;
  color: #909399;
  margin-top: 2px;
}
.count {
  font-size: 13px;
  color: #909399;
}
.task-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 4px;
  border-bottom: 1px solid #f0f2f5;
}
.task-row.done .task-title {
  text-decoration: line-through;
  color: #c0c4cc;
}
.task-main {
  flex: 1;
  min-width: 0;
}
.task-title {
  font-size: 14px;
  color: #303133;
}
.task-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
  flex-wrap: wrap;
}
.overdue {
  color: #f56c6c;
  font-weight: 600;
}
.detail {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}
/* 日历 */
.cal-cell {
  height: 100%;
  padding: 2px;
  overflow: hidden;
}
.cal-day {
  font-size: 12px;
  color: #606266;
}
.cal-task {
  font-size: 11px;
  line-height: 1.5;
  padding: 0 4px;
  margin-top: 2px;
  border-radius: 3px;
  background: #ecf5ff;
  color: #409eff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}
.cal-task.cal-overdue {
  background: #fef0f0;
  color: #f56c6c;
}
.cal-task.cal-done {
  background: #f4f4f5;
  color: #c0c4cc;
  text-decoration: line-through;
}
.cal-legend {
  display: flex;
  gap: 16px;
  align-items: center;
  padding-top: 8px;
  font-size: 12px;
  color: #909399;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.dot-normal {
  background: #409eff;
}
.dot-overdue {
  background: #f56c6c;
}
.dot-done {
  background: #c0c4cc;
}
.legend-tip {
  margin-left: auto;
}
</style>
