import client from './client'

// ---- 认证 ----
export const register = (data) => client.post('/auth/register', data)
export const login = (data) => client.post('/auth/login', data)
export const getMe = () => client.get('/auth/me')
export const updateMe = (data) => client.put('/auth/me', data)

// ---- 课程 ----
export const listCourses = () => client.get('/courses')
export const createCourse = (data) => client.post('/courses', data)
export const getCourse = (id) => client.get(`/courses/${id}`)
export const updateCourse = (id, data) => client.put(`/courses/${id}`, data)
export const deleteCourse = (id) => client.delete(`/courses/${id}`)
export const knowledgeSummary = (id) => client.post(`/courses/${id}/knowledge-summary`)

// ---- 资料 ----
export const listMaterials = (courseId, params = {}) =>
  client.get(`/courses/${courseId}/materials`, { params })
export const uploadMaterial = (courseId, formData) =>
  client.post(`/courses/${courseId}/materials`, formData)
export const searchMaterialContent = (courseId, q) =>
  client.get(`/courses/${courseId}/materials/search`, { params: { q } })
export const deleteMaterial = (id) => client.delete(`/materials/${id}`)
export const materialDownloadUrl = (id) => `/api/materials/${id}/download`

// ---- 对话 ----
export const listCourseConversations = (courseId) =>
  client.get(`/courses/${courseId}/conversations`)
export const listAllConversations = () => client.get('/conversations')
export const createConversation = (courseId, data = {}) =>
  client.post(`/courses/${courseId}/conversations`, data)
export const listMessages = (convId) => client.get(`/conversations/${convId}/messages`)
export const sendMessage = (convId, content) =>
  client.post(`/conversations/${convId}/messages`, { content })
export const deleteConversation = (convId) => client.delete(`/conversations/${convId}`)

/**
 * 流式发送消息（SSE over fetch）。
 * 事件回调：onMeta({ user_message_id })、onDelta(text)、
 *          onTool({ name, input })、onDone({ agent_mode, citations })。
 */
export async function sendMessageStream(
  convId,
  content,
  { onMeta, onDelta, onTool, onDone } = {},
) {
  const token = localStorage.getItem('token')
  const resp = await fetch(`/api/conversations/${convId}/messages/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ content }),
  })
  if (!resp.ok) {
    let detail = '发送失败，请稍后重试'
    try {
      const body = await resp.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* 非 JSON 错误体，使用默认提示 */
    }
    throw new Error(detail)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const handleFrame = (frame) => {
    let event = 'message'
    let data = ''
    for (const line of frame.split('\n')) {
      if (line.startsWith('event: ')) event = line.slice(7).trim()
      else if (line.startsWith('data: ')) data += line.slice(6)
    }
    if (!data) return
    const payload = JSON.parse(data)
    if (event === 'meta') onMeta?.(payload)
    else if (event === 'delta') onDelta?.(payload.text)
    else if (event === 'tool') onTool?.(payload)
    else if (event === 'done') onDone?.(payload)
  }
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      handleFrame(buffer.slice(0, sep))
      buffer = buffer.slice(sep + 2)
    }
  }
}

// ---- 学习计划 ----
export const listPlans = () => client.get('/plans')
export const createPlan = (data) => client.post('/plans', data)
export const createMultiPlan = (data) => client.post('/plans/multi-course', data)
export const deletePlan = (id) => client.delete(`/plans/${id}`)

// ---- 待办任务 ----
export const listTasks = (params = {}) => client.get('/tasks', { params })
export const getTaskReminders = () => client.get('/tasks/reminders')
export const createTask = (data) => client.post('/tasks', data)
export const updateTask = (id, data) => client.put(`/tasks/${id}`, data)
export const deleteTask = (id) => client.delete(`/tasks/${id}`)
