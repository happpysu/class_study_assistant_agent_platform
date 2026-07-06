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

// ---- 学习计划 ----
export const listPlans = () => client.get('/plans')
export const createPlan = (data) => client.post('/plans', data)
export const createMultiPlan = (data) => client.post('/plans/multi-course', data)
export const deletePlan = (id) => client.delete(`/plans/${id}`)

// ---- 待办任务 ----
export const listTasks = (params = {}) => client.get('/tasks', { params })
export const createTask = (data) => client.post('/tasks', data)
export const updateTask = (id, data) => client.put(`/tasks/${id}`, data)
export const deleteTask = (id) => client.delete(`/tasks/${id}`)
