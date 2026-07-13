import DOMPurify from 'dompurify'
import { marked } from 'marked'

/** 将 Agent 生成的 Markdown 转成经过消毒、可安全用于 v-html 的 HTML。 */
export function renderMarkdown(text) {
  return DOMPurify.sanitize(marked.parse(text || ''))
}
