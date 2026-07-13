<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createConversation,
  deleteConversation,
  getCourse,
  listCourseConversations,
  listMessages,
  sendMessageStream,
} from '../api'
import { renderMarkdown } from '../utils/markdown'

const route = useRoute()
const router = useRouter()
const courseId = Number(route.params.id)

const course = ref(null)
const conversations = ref([])
const activeConvId = ref(null)
const messages = ref([])
const input = ref('')
const sending = ref(false)
const lastAgentMode = ref('')
const msgListEl = ref(null)

function toolLabel(tool) {
  const input = tool.input || {}
  switch (tool.name) {
    case 'search_course_materials':
      return `检索课程资料「${input.query ?? ''}」`
    case 'list_materials':
      return '查看资料清单'
    case 'read_material':
      return `阅读资料 #${input.material_id ?? ''}`
    case 'list_courses':
      return '查看课程列表'
    case 'create_course':
      return `创建课程「${input.name ?? ''}」`
    case 'list_tasks':
      return '查看待办任务'
    case 'create_task':
      return `创建任务「${input.title ?? ''}」${input.due_date ? `（${input.due_date}）` : ''}`
    case 'update_task':
      return `更新任务 #${input.task_id ?? ''}`
    case 'delete_task':
      return `删除任务 #${input.task_id ?? ''}`
    case 'create_study_plan':
      return `保存学习计划「${input.goal ?? ''}」（${(input.daily_tasks || []).length} 项每日任务）`
    default:
      return `调用工具 ${tool.name}`
  }
}

async function refreshConversations() {
  const { data } = await listCourseConversations(courseId)
  conversations.value = data
}

async function openConversation(id) {
  activeConvId.value = id
  const { data } = await listMessages(id)
  messages.value = data
  scrollToBottom()
}

async function newConversation() {
  const { data } = await createConversation(courseId)
  await refreshConversations()
  await openConversation(data.id)
}

async function removeConversation(conv) {
  await ElMessageBox.confirm(`删除对话「${conv.title}」？`, '删除确认', { type: 'warning' })
  await deleteConversation(conv.id)
  if (activeConvId.value === conv.id) {
    activeConvId.value = null
    messages.value = []
  }
  await refreshConversations()
}

async function send() {
  const content = input.value.trim()
  if (!content || sending.value) return
  if (!activeConvId.value) {
    await newConversation()
  }
  input.value = ''
  const userMsg = { id: `tmp-u-${Date.now()}`, role: 'user', content, citations: [] }
  const assistantMsg = {
    id: `tmp-a-${Date.now()}`,
    role: 'assistant',
    content: '',
    citations: [],
    toolEvents: [],
    streaming: true,
  }
  messages.value.push(userMsg, assistantMsg)
  scrollToBottom()
  sending.value = true
  try {
    await sendMessageStream(activeConvId.value, content, {
      onMeta: (meta) => {
        userMsg.id = meta.user_message_id
      },
      onDelta: (text) => {
        assistantMsg.content += text
        scrollToBottom()
      },
      onTool: (tool) => {
        assistantMsg.toolEvents.push(toolLabel(tool))
        scrollToBottom()
      },
      onDone: (result) => {
        assistantMsg.id = result.assistant_message_id
        assistantMsg.citations = result.citations || []
        assistantMsg.streaming = false
        lastAgentMode.value = result.agent_mode
      },
    })
    await refreshConversations()
  } catch (err) {
    messages.value = messages.value.filter((m) => m !== userMsg && m !== assistantMsg)
    input.value = content
    ElMessage.error(err.message || '发送失败，请稍后重试')
  } finally {
    assistantMsg.streaming = false
    sending.value = false
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (msgListEl.value) msgListEl.value.scrollTop = msgListEl.value.scrollHeight
  })
}

onMounted(async () => {
  const { data } = await getCourse(courseId)
  course.value = data
  await refreshConversations()
  if (conversations.value.length) {
    await openConversation(conversations.value[0].id)
  }
})
</script>

<template>
  <div class="chat-page">
    <el-page-header @back="router.push(`/courses/${courseId}`)">
      <template #content>
        <span class="title">{{ course?.name }} · Agent 问答</span>
        <el-tag v-if="lastAgentMode === 'fallback'" type="warning" size="small" class="ml">
          离线模式
        </el-tag>
      </template>
    </el-page-header>

    <div class="chat-body">
      <div class="conv-panel">
        <el-button type="primary" plain class="new-btn" @click="newConversation">
          <el-icon><Plus /></el-icon>新建对话
        </el-button>
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="conv-item"
          :class="{ active: conv.id === activeConvId }"
          @click="openConversation(conv.id)"
        >
          <span class="conv-title">{{ conv.title }}</span>
          <el-icon class="conv-del" @click.stop="removeConversation(conv)"><Delete /></el-icon>
        </div>
      </div>

      <div class="msg-panel">
        <div ref="msgListEl" class="msg-list">
          <el-empty
            v-if="!messages.length"
            description="向 Agent 提问或下达指令：它会自主检索资料回答（带引用），也能帮你拆解目标、创建待办任务"
          />
          <div v-for="msg in messages" :key="msg.id" class="msg" :class="msg.role">
            <div class="bubble">
              <template v-if="msg.role === 'assistant'">
                <div v-if="msg.toolEvents?.length" class="tools">
                  <div v-for="(label, i) in msg.toolEvents" :key="i" class="tool-line">
                    🔧 {{ label }}
                  </div>
                </div>
                <div v-if="msg.content" class="md" v-html="renderMarkdown(msg.content)" />
                <span v-else-if="msg.streaming" class="typing">思考中…</span>
              </template>
              <template v-else>{{ msg.content }}</template>
              <div v-if="msg.citations?.length" class="citations">
                <div class="citations-title">📎 参考资料：</div>
                <el-tooltip
                  v-for="c in msg.citations"
                  :key="c.index"
                  :content="c.excerpt"
                  placement="top"
                >
                  <el-tag size="small" class="citation-tag">
                    [{{ c.index }}] {{ c.material_name }}
                  </el-tag>
                </el-tooltip>
              </div>
            </div>
          </div>
        </div>
        <div class="input-row">
          <el-input
            v-model="input"
            type="textarea"
            :rows="2"
            placeholder="输入问题，Enter 发送（Shift+Enter 换行）"
            @keydown.enter.exact.prevent="send"
          />
          <el-button type="primary" :loading="sending" @click="send">发送</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  height: calc(100vh - 100px);
  display: flex;
  flex-direction: column;
}
.title {
  font-size: 18px;
  font-weight: 600;
}
.ml {
  margin-left: 8px;
}
.chat-body {
  flex: 1;
  display: flex;
  gap: 16px;
  margin-top: 16px;
  min-height: 0;
}
.conv-panel {
  width: 220px;
  background: #fff;
  border-radius: 8px;
  padding: 12px;
  overflow-y: auto;
}
.new-btn {
  width: 100%;
  margin-bottom: 12px;
}
.conv-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #606266;
}
.conv-item:hover {
  background: #f5f7fa;
}
.conv-item.active {
  background: #ecf5ff;
  color: #409eff;
}
.conv-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conv-del {
  flex-shrink: 0;
  opacity: 0;
}
.conv-item:hover .conv-del {
  opacity: 1;
}
.msg-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  min-width: 0;
}
.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.msg {
  display: flex;
  margin-bottom: 12px;
}
.msg.user {
  justify-content: flex-end;
}
.bubble {
  max-width: 72%;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.user .bubble {
  background: #409eff;
  color: #fff;
}
.msg.assistant .bubble {
  background: #f4f4f5;
  color: #303133;
  white-space: normal;
}
.typing {
  color: #909399;
}
.tools {
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #dcdfe6;
}
.tool-line {
  font-size: 12px;
  color: #909399;
  line-height: 1.8;
}
.citations {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #dcdfe6;
}
.citations-title {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.citation-tag {
  margin: 2px 4px 2px 0;
  cursor: default;
}
.md :deep(p) {
  margin: 4px 0;
}
.input-row {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #e4e7ed;
}
</style>
