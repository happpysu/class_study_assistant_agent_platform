import axios from 'axios'
import { ElMessage } from 'element-plus'

const client = axios.create({ baseURL: '/api', timeout: 120000 })

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail
    if (status === 401) {
      localStorage.removeItem('token')
      if (!location.hash.includes('/login')) location.hash = '#/login'
    }
    ElMessage.error(
      typeof detail === 'string' ? detail : (detail?.[0]?.msg ?? '请求失败，请稍后重试'),
    )
    return Promise.reject(error)
  },
)

export default client
