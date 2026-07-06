<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createTask, deleteTask, listCourses, listTasks, updateTask } from '../api'

const tasks = ref([])
const courses = ref([])
const filterStatus = ref('todo') // todo / done / all
const form = reactive({ title: '', detail: '', course_id: null, due_date: '' })

async function refresh() {
  const params = {}
  if (filterStatus.value === 'todo') params.completed = false
  if (filterStatus.value === 'done') params.completed = true
  const [{ data: taskData }, { data: courseData }] = await Promise.all([
    listTasks(params),
    listCourses(),
  ])
  tasks.value = taskData
  courses.value = courseData
}
onMounted(refresh)

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
const isOverdue = (task) =>
  !task.completed && task.due_date && task.due_date < new Date().toISOString().slice(0, 10)
const todoCount = computed(() => tasks.value.filter((t) => !t.completed).length)
</script>

<template>
  <div>
    <div class="toolbar">
      <h3>待办任务</h3>
      <el-radio-group v-model="filterStatus" @change="refresh">
        <el-radio-button value="todo">未完成</el-radio-button>
        <el-radio-button value="done">已完成</el-radio-button>
        <el-radio-button value="all">全部</el-radio-button>
      </el-radio-group>
    </div>

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

    <el-card>
      <template #header>
        任务列表<span v-if="filterStatus !== 'done'" class="count">（{{ todoCount }} 项未完成）</span>
      </template>
      <el-empty v-if="!tasks.length" description="暂无任务" />
      <div v-for="task in tasks" :key="task.id" class="task-row" :class="{ done: task.completed }">
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
.block {
  margin-bottom: 16px;
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
</style>
