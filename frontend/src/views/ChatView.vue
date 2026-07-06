<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { marked } from 'marked'
import {
  createConversation,
  deleteConversation,
  getCourse,
  listCourseConversations,
  listMessages,
  sendMessage,
} from '../api'

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

const renderMd = (text) => marked.parse(text || '')

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
  messages.value = [
    ...messages.value,
    { id: `tmp-${Date.now()}`, role: 'user', content, citations: [] },
  ]
  scrollToBottom()
  sending.value = true
  try {
    const { data } = await sendMessage(activeConvId.value, content)
    lastAgentMode.value = data.agent_mode
    messages.value = [
      ...messages.value.slice(0, -1),
      data.user_message,
      data.assistant_message,
    ]
    scrollToBottom()
    await refreshConversations()
  } catch {
    messages.value = messages.value.slice(0, -1)
    input.value = content
  } finally {
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
            description="围绕本课程的资料向 Agent 提问吧，例如：第二章的重点是什么？"
          />
          <div v-for="msg in messages" :key="msg.id" class="msg" :class="msg.role">
            <div class="bubble">
              <div v-if="msg.role === 'assistant'" class="md" v-html="renderMd(msg.content)" />
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
          <div v-if="sending" class="msg assistant">
            <div class="bubble typing">思考中…</div>
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
