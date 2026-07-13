import { describe, expect, it } from 'vitest'

import { renderMarkdown } from './markdown'

describe('renderMarkdown', () => {
  it('保留正常 Markdown 格式', () => {
    const html = renderMarkdown('## 标题\n\n**重点**')

    expect(html).toContain('<h2>标题</h2>')
    expect(html).toContain('<strong>重点</strong>')
  })

  it('移除脚本和危险属性', () => {
    const html = renderMarkdown(
      '<img src=x onerror="alert(1)"><script>alert(2)</script>[链接](javascript:alert(3))',
    )

    expect(html).not.toContain('onerror')
    expect(html).not.toContain('<script')
    expect(html).not.toContain('javascript:')
  })
})
