<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { marked } from 'marked'
import {
  deleteMaterial,
  getCourse,
  knowledgeSummary,
  listMaterials,
  materialDownloadUrl,
  searchMaterialContent,
  uploadMaterial,
} from '../api'

const route = useRoute()
const router = useRouter()
const courseId = Number(route.params.id)

const course = ref(null)
const materials = ref([])
const filter = reactive({ mtype: '', keyword: '' })
const uploadForm = reactive({ mtype: 'courseware', description: '', file: null })
const uploading = ref(false)
const searchQuery = ref('')
const searchHits = ref([])
const summary = ref('')
const summaryMode = ref('')
const summarizing = ref(false)

const typeLabels = {
  courseware: '课件',
  notes: '教材笔记',
  assignment: '作业要求',
  lab: '实验指导',
  other: '其他',
}
const summaryHtml = computed(() => (summary.value ? marked.parse(summary.value) : ''))

async function refreshMaterials() {
  const params = {}
  if (filter.mtype) params.mtype = filter.mtype
  if (filter.keyword) params.keyword = filter.keyword
  const { data } = await listMaterials(courseId, params)
  materials.value = data
}

onMounted(async () => {
  const { data } = await getCourse(courseId)
  course.value = data
  await refreshMaterials()
})

function onFileChange(file) {
  uploadForm.file = file.raw
}

async function submitUpload() {
  if (!uploadForm.file) {
    ElMessage.warning('请先选择文件')
    return
  }
  const formData = new FormData()
  formData.append('file', uploadForm.file)
  formData.append('mtype', uploadForm.mtype)
  formData.append('description', uploadForm.description)
  uploading.value = true
  try {
    await uploadMaterial(courseId, formData)
    ElMessage.success('上传成功（txt/md/pdf 已自动解析入库供 Agent 引用）')
    uploadForm.file = null
    uploadForm.description = ''
    await refreshMaterials()
  } finally {
    uploading.value = false
  }
}

async function removeMaterial(m) {
  await ElMessageBox.confirm(`确定删除资料「${m.filename}」？`, '删除确认', {
    type: 'warning',
  })
  await deleteMaterial(m.id)
  ElMessage.success('已删除')
  await refreshMaterials()
}

async function doSearch() {
  if (!searchQuery.value.trim()) return
  const { data } = await searchMaterialContent(courseId, searchQuery.value)
  searchHits.value = data
  if (!data.length) ElMessage.info('未检索到相关内容')
}

async function generateSummary() {
  summarizing.value = true
  try {
    const { data } = await knowledgeSummary(courseId)
    summary.value = data.summary
    summaryMode.value = data.agent_mode
  } finally {
    summarizing.value = false
  }
}

function download(m) {
  const token = localStorage.getItem('token')
  fetch(materialDownloadUrl(m.id), { headers: { Authorization: `Bearer ${token}` } })
    .then((r) => r.blob())
    .then((blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = m.filename
      a.click()
      URL.revokeObjectURL(url)
    })
}
</script>

<template>
  <div v-if="course">
    <el-page-header @back="router.push('/courses')">
      <template #content>
        <span class="title">{{ course.name }}</span>
        <el-tag v-if="course.semester" size="small" class="ml">{{ course.semester }}</el-tag>
      </template>
      <template #extra>
        <el-button type="primary" @click="router.push(`/courses/${courseId}/chat`)">
          <el-icon><ChatDotRound /></el-icon>Agent 问答
        </el-button>
      </template>
    </el-page-header>

    <el-tabs class="tabs">
      <el-tab-pane label="资料管理">
        <el-card class="block">
          <template #header>上传资料</template>
          <div class="upload-row">
            <el-upload
              :auto-upload="false"
              :show-file-list="Boolean(uploadForm.file)"
              :limit="1"
              :on-change="onFileChange"
              :on-remove="() => (uploadForm.file = null)"
            >
              <el-button>选择文件</el-button>
            </el-upload>
            <el-select v-model="uploadForm.mtype" style="width: 140px">
              <el-option
                v-for="(label, value) in typeLabels"
                :key="value"
                :label="label"
                :value="value"
              />
            </el-select>
            <el-input
              v-model="uploadForm.description"
              placeholder="资料说明（选填）"
              style="width: 240px"
            />
            <el-button type="primary" :loading="uploading" @click="submitUpload">上传</el-button>
          </div>
        </el-card>

        <el-card class="block">
          <template #header>
            <div class="filter-row">
              <span>资料列表</span>
              <div class="filters">
                <el-select v-model="filter.mtype" clearable placeholder="全部类型" style="width: 130px" @change="refreshMaterials">
                  <el-option v-for="(label, value) in typeLabels" :key="value" :label="label" :value="value" />
                </el-select>
                <el-input v-model="filter.keyword" placeholder="按文件名/说明筛选" clearable style="width: 200px" @change="refreshMaterials" />
              </div>
            </div>
          </template>
          <el-table :data="materials" empty-text="暂无资料">
            <el-table-column prop="filename" label="文件名" min-width="180" />
            <el-table-column label="类型" width="110">
              <template #default="{ row }">
                <el-tag size="small">{{ typeLabels[row.mtype] || row.mtype }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="说明" min-width="140" show-overflow-tooltip />
            <el-table-column label="大小" width="100">
              <template #default="{ row }">{{ (row.size_bytes / 1024).toFixed(1) }} KB</template>
            </el-table-column>
            <el-table-column label="操作" width="160">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="download(row)">下载</el-button>
                <el-button size="small" link type="danger" @click="removeMaterial(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="block">
          <template #header>资料内容检索</template>
          <div class="upload-row">
            <el-input
              v-model="searchQuery"
              placeholder="输入关键词，在资料正文中检索相关片段"
              style="width: 320px"
              @keyup.enter="doSearch"
            />
            <el-button type="primary" @click="doSearch">检索</el-button>
          </div>
          <div v-for="hit in searchHits" :key="hit.chunk_id" class="hit">
            <div class="hit-source">《{{ hit.material_name }}》 · 匹配度 {{ hit.score }}</div>
            <div class="hit-text">{{ hit.excerpt }}…</div>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="知识点整理">
        <el-card class="block">
          <template #header>
            <div class="filter-row">
              <span>复习提纲（根据课程资料自动提取重点知识点）</span>
              <el-button type="primary" :loading="summarizing" @click="generateSummary">
                {{ summarizing ? '生成中…' : '生成知识点提纲' }}
              </el-button>
            </div>
          </template>
          <el-alert
            v-if="summaryMode === 'fallback'"
            type="warning"
            :closable="false"
            class="block"
            title="当前为离线模式（未配置大模型 API Key），仅展示资料片段目录"
          />
          <div v-if="summary" class="markdown" v-html="summaryHtml" />
          <el-empty v-else description="点击右上角按钮生成知识点提纲" />
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.title {
  font-size: 18px;
  font-weight: 600;
}
.ml {
  margin-left: 8px;
}
.tabs {
  margin-top: 16px;
}
.block {
  margin-bottom: 16px;
}
.upload-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}
.filter-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filters {
  display: flex;
  gap: 8px;
}
.hit {
  padding: 10px 0;
  border-bottom: 1px dashed #e4e7ed;
}
.hit-source {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.hit-text {
  font-size: 13px;
  color: #303133;
}
.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3) {
  margin: 12px 0 6px;
}
.markdown :deep(p),
.markdown :deep(li) {
  line-height: 1.7;
  font-size: 14px;
}
</style>
