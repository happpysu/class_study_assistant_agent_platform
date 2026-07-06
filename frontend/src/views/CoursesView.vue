<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createCourse, deleteCourse, listCourses, updateCourse } from '../api'

const router = useRouter()
const courses = ref([])
const dialogVisible = ref(false)
const editingId = ref(null)
const form = reactive({ name: '', description: '', teacher: '', semester: '' })

async function refresh() {
  const { data } = await listCourses()
  courses.value = data
}
onMounted(refresh)

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', description: '', teacher: '', semester: '' })
  dialogVisible.value = true
}

function openEdit(course) {
  editingId.value = course.id
  Object.assign(form, course)
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写课程名称')
    return
  }
  const payload = {
    name: form.name,
    description: form.description,
    teacher: form.teacher,
    semester: form.semester,
  }
  if (editingId.value) {
    await updateCourse(editingId.value, payload)
  } else {
    await createCourse(payload)
  }
  dialogVisible.value = false
  ElMessage.success('保存成功')
  await refresh()
}

async function remove(course) {
  await ElMessageBox.confirm(
    `删除课程《${course.name}》将同时删除其资料与对话记录，确定吗？`,
    '删除确认',
    { type: 'warning' },
  )
  await deleteCourse(course.id)
  ElMessage.success('已删除')
  await refresh()
}
</script>

<template>
  <div>
    <div class="toolbar">
      <h3>我的课程</h3>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>新建课程
      </el-button>
    </div>

    <el-empty v-if="!courses.length" description="还没有课程，点击右上角创建第一门课程吧" />

    <el-row :gutter="16">
      <el-col v-for="course in courses" :key="course.id" :xs="24" :sm="12" :md="8" :lg="6">
        <el-card class="course-card" shadow="hover" @click="router.push(`/courses/${course.id}`)">
          <div class="course-name">{{ course.name }}</div>
          <div class="course-meta">
            <el-tag v-if="course.semester" size="small">{{ course.semester }}</el-tag>
            <span v-if="course.teacher" class="teacher">{{ course.teacher }}</span>
          </div>
          <div class="course-desc">{{ course.description || '暂无简介' }}</div>
          <div class="course-actions" @click.stop>
            <el-button size="small" @click="router.push(`/courses/${course.id}/chat`)">
              <el-icon><ChatDotRound /></el-icon>问答
            </el-button>
            <el-button size="small" @click="openEdit(course)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="remove(course)">删除</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑课程' : '新建课程'"
      width="480px"
    >
      <el-form label-width="80px">
        <el-form-item label="课程名称" required>
          <el-input v-model="form.name" maxlength="128" />
        </el-form-item>
        <el-form-item label="授课教师">
          <el-input v-model="form.teacher" maxlength="64" />
        </el-form-item>
        <el-form-item label="学期">
          <el-input v-model="form.semester" placeholder="如 2026春" maxlength="32" />
        </el-form-item>
        <el-form-item label="课程简介">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="2000" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
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
.course-card {
  margin-bottom: 16px;
  cursor: pointer;
}
.course-name {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}
.course-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.teacher {
  font-size: 13px;
  color: #909399;
}
.course-desc {
  font-size: 13px;
  color: #606266;
  min-height: 36px;
  margin-bottom: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
