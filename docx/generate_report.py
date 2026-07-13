"""由 Markdown 源文件生成学校格式的课程设计报告 DOCX。"""
from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "课程学习助手Agent平台设计报告.md"
OUTPUT = ROOT / "课程学习助手Agent平台设计报告.docx"
TEMPLATE = ROOT / "实践报告模板.docx"
BODY_STYLE = "报告正文"
HEADING_STYLES = {
    1: "报告一级标题",
    2: "报告二级标题",
    3: "报告三级标题",
}

PROJECT_NAME = "课程学习助手 Agent 平台"
COLLEGE = "网络空间安全学院"
TEACHER = "昌硕"


def set_run_font(run, name="宋体", size=10.5, bold=False, color=None, east_asia=None):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east_asia or name)
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=90, start=90, bottom=90, end=90):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_cell_text(cell, text, *, size=10.5, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.15
    set_run_font(paragraph.add_run(text), size=size, bold=bold)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    set_cell_margins(cell)


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_table_borders(table):
    """为正文表格添加单实线网格，不依赖旧模板中不存在的 Table Grid 样式。"""
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = borders.find(qn(f"w:{edge}"))
        if border is None:
            border = OxmlElement(f"w:{edge}")
            borders.append(border)
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "4")
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), "auto")


def add_field(paragraph, instruction):
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run = paragraph.add_run()
    run._r.extend([begin, instr, separate, end])


def replace_run_properties(run, source_rpr):
    """用模板的原始 rPr 替换当前文字属性。

    这会保留模板中的中西文字体分配、字号、加粗和自动颜色，
    避免通过 python-docx 重建样式时丢失 szCs、lang 等 Word 属性。
    """
    current = run._r.rPr
    if current is not None:
        run._r.remove(current)
    run._r.insert(0, deepcopy(source_rpr))


def replace_style_run_properties(style, source_rpr):
    current = style._element.rPr
    if current is not None:
        style._element.remove(current)
    style._element.append(deepcopy(source_rpr))


def configure_styles(doc, template_heading_rpr):
    styles = doc.styles

    # 不修改 Normal：封面标题和表格都使用模板原有 Normal，
    # 改动它会间接改变开头表格。正文单独使用自定义样式。
    try:
        body = styles[BODY_STYLE]
    except KeyError:
        body = styles.add_style(BODY_STYLE, WD_STYLE_TYPE.PARAGRAPH)
    body.base_style = styles["Normal"]
    body.font.name = "宋体"
    body._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "宋体")
    body.font.size = Pt(10.5)
    pf = body.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.space_after = Pt(0)
    pf.first_line_indent = Pt(21)
    pf.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # 模板本身没有 1—3 级标题样式，因此建立带大纲级别的报告标题样式，
    # 其字符属性直接复制自模板“课程设计目的”。
    for level, style_name in HEADING_STYLES.items():
        try:
            style = styles[style_name]
        except KeyError:
            style = styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
        style.base_style = styles["Normal"]
        replace_style_run_properties(style, template_heading_rpr)
        style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        style.paragraph_format.first_line_indent = Pt(0)
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = Pt(0)
        style.paragraph_format.keep_with_next = True
        p_pr = style._element.get_or_add_pPr()
        outline = p_pr.find(qn("w:outlineLvl"))
        if outline is None:
            outline = OxmlElement("w:outlineLvl")
            p_pr.append(outline)
        outline.set(qn("w:val"), str(level - 1))


def configure_page(section, *, body=False):
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.50119)
    section.right_margin = Cm(2.50119)
    section.header_distance = Cm(1.50107)
    section.footer_distance = Cm(1.74978)
    if body:
        section.header.is_linked_to_previous = False
        section.footer.is_linked_to_previous = False
        header = section.header.paragraphs[0]
        header.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(header.add_run("北京邮电大学大型程序设计实践报告"), "宋体", 9)
        footer = section.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(footer.add_run("第 "), "宋体", 9)
        add_field(footer, " PAGE ")
        set_run_font(footer.add_run(" 页  共 "), "宋体", 9)
        add_field(footer, " SECTIONPAGES ")
        set_run_font(footer.add_run(" 页"), "宋体", 9)
        sect_pr = section._sectPr
        pg_num = sect_pr.find(qn("w:pgNumType"))
        if pg_num is None:
            pg_num = OxmlElement("w:pgNumType")
            sect_pr.append(pg_num)
        pg_num.set(qn("w:start"), "1")


def add_cover(doc):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(35)
    p.paragraph_format.space_after = Pt(28)
    set_run_font(p.add_run("北京邮电大学设计实践报告"), "文鼎大标宋简", 22, True)

    table = doc.add_table(rows=6, cols=6)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = True

    set_cell_text(table.cell(0, 0), "系统设计名称", bold=True)
    project_cell = table.cell(0, 1).merge(table.cell(0, 3))
    set_cell_text(project_cell, PROJECT_NAME, size=14, bold=True)
    set_cell_text(table.cell(0, 4), "指导教师", bold=True)
    set_cell_text(table.cell(0, 5), TEACHER)

    set_cell_text(table.cell(1, 0), "学 院", bold=True)
    college_cell = table.cell(1, 1).merge(table.cell(1, 2))
    set_cell_text(college_cell, COLLEGE)
    set_cell_text(table.cell(1, 3), "完成日期", bold=True)
    date_cell = table.cell(1, 4).merge(table.cell(1, 5))
    set_cell_text(date_cell, "2026 年 7 月")

    headers = ["班级", "班内序号", "学号", "学生姓名", "主要分工", "成绩"]
    for col, value in enumerate(headers):
        set_cell_text(table.cell(2, col), value, bold=True)
        set_cell_shading(table.cell(2, col), "D9EAF7")
    for row in range(3, 6):
        for col in range(6):
            set_cell_text(table.cell(row, col), "")

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(16)
    set_run_font(p.add_run("系统设计内容"), "幼圆", 16, True, east_asia="微软雅黑")
    content_table = doc.add_table(rows=1, cols=1)
    content_table.style = "Table Grid"
    text = (
        "设计并实现课程学习助手 Agent 平台，完成用户认证、课程与资料管理、"
        "基于课程资料的 Agent 问答、知识点整理、学习计划、待办任务、资料来源引用、"
        "智能任务拆解和多课程学习规划。"
    )
    set_cell_text(content_table.cell(0, 0), text, size=11)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(26)
    set_run_font(p.add_run("注：成员信息与成绩栏请在提交前按实际情况填写。"), "宋体", 9)

    doc.add_page_break()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_run_font(p.add_run("设计成绩评定"), "幼圆", 16, True, east_asia="微软雅黑")
    grade = doc.add_table(rows=2, cols=1)
    grade.style = "Table Grid"
    set_cell_text(grade.cell(0, 0), "指导教师评语", size=12, bold=True)
    grade.cell(1, 0).text = "\n" * 20 + "指导教师签名：________________\n\n年    月    日"
    for paragraph in grade.cell(1, 0).paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        paragraph.paragraph_format.first_line_indent = Pt(0)
        for run in paragraph.runs:
            set_run_font(run, size=11)
    p = doc.add_paragraph()
    set_run_font(p.add_run("注：评语应体现每位学生的实际工作情况，可以加页。"), "宋体", 9)


def add_toc(doc):
    p = doc.add_paragraph(style=BODY_STYLE)
    p.paragraph_format.first_line_indent = Pt(0)
    add_field(p, ' TOC \\o "1-3" \\h \\z \\u ')


INLINE_RE = re.compile(r"(\*\*.+?\*\*|`.+?`)")
IMAGE_RE = re.compile(r"^!\[(.+?)\]\((.+?)\)$")


def add_inline(paragraph, text, *, default_size=10.5):
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            set_run_font(paragraph.add_run(part[2:-2]), size=default_size, bold=True)
        elif part.startswith("`") and part.endswith("`"):
            set_run_font(paragraph.add_run(part[1:-1]), "Courier New", default_size - 1)
        else:
            set_run_font(paragraph.add_run(part), size=default_size)


def add_body_paragraph(doc, text):
    if text.startswith("图 ") or text.startswith("表 "):
        p = doc.add_paragraph(style=BODY_STYLE)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(4)
        add_inline(p, text, default_size=10)
        return
    p = doc.add_paragraph(style=BODY_STYLE)
    add_inline(p, text)


def add_figure(doc, image_path, caption):
    """按正文可用宽度插入真实运行截图和左对齐图题。"""
    path = (SOURCE.parent / image_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"截图不存在: {path}")

    picture = doc.add_paragraph(style=BODY_STYLE)
    picture.alignment = WD_ALIGN_PARAGRAPH.LEFT
    picture.paragraph_format.first_line_indent = Pt(0)
    picture.paragraph_format.space_before = Pt(5)
    picture.paragraph_format.space_after = Pt(2)
    picture.paragraph_format.keep_with_next = True
    picture.add_run().add_picture(str(path), width=Cm(15.7))

    caption_paragraph = doc.add_paragraph(style=BODY_STYLE)
    caption_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    caption_paragraph.paragraph_format.first_line_indent = Pt(0)
    caption_paragraph.paragraph_format.space_before = Pt(0)
    caption_paragraph.paragraph_format.space_after = Pt(6)
    add_inline(caption_paragraph, caption, default_size=10)


def add_list_item(doc, text, marker="•"):
    p = doc.add_paragraph(style=BODY_STYLE)
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.left_indent = Cm(0.75)
    p.paragraph_format.space_after = Pt(2)
    add_inline(p, f"{marker} {text}")


def add_quote(doc, text):
    p = doc.add_paragraph(style=BODY_STYLE)
    p.paragraph_format.left_indent = Cm(0.8)
    p.paragraph_format.right_indent = Cm(0.5)
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.space_before = Pt(5)
    p.paragraph_format.space_after = Pt(5)
    p_pr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), "FFF2CC")
    p_pr.append(shd)
    add_inline(p, text, default_size=10)


def add_code(doc, lines):
    p = doc.add_paragraph(style=BODY_STYLE)
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.left_indent = Cm(0.4)
    p.paragraph_format.right_indent = Cm(0.4)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.0
    p_pr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), "F2F2F2")
    p_pr.append(shd)
    for index, line in enumerate(lines):
        run = p.add_run(line)
        set_run_font(run, "Courier New", 8.5)
        if index < len(lines) - 1:
            run.add_break()


def parse_table_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def add_markdown_table(doc, rows):
    if len(rows) >= 2 and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in rows[1]):
        rows = [rows[0], *rows[2:]]
    if not rows:
        return
    columns = max(len(row) for row in rows)
    table = doc.add_table(rows=len(rows), cols=columns)
    table.style = "Normal Table"
    set_table_borders(table)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = True
    for r_index, row in enumerate(rows):
        for c_index in range(columns):
            value = row[c_index] if c_index < len(row) else ""
            cell = table.cell(r_index, c_index)
            set_cell_text(
                cell,
                value,
                size=9,
                bold=r_index == 0,
                align=WD_ALIGN_PARAGRAPH.LEFT,
            )
            if r_index == 0:
                set_cell_shading(cell, "D9EAF7")
    set_repeat_table_header(table.rows[0])
    doc.add_paragraph(style=BODY_STYLE).paragraph_format.space_after = Pt(0)


def render_markdown(doc, source, template_heading_rpr):
    lines = source.splitlines()
    index = 0
    paragraph_buffer = []

    def flush_paragraph():
        nonlocal paragraph_buffer
        if paragraph_buffer:
            add_body_paragraph(doc, "".join(part.strip() for part in paragraph_buffer))
            paragraph_buffer = []

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        if stripped == "<!-- pagebreak -->":
            flush_paragraph()
            doc.add_page_break()
            index += 1
            continue
        if stripped == "[TOC]":
            flush_paragraph()
            add_toc(doc)
            index += 1
            continue
        image_match = IMAGE_RE.match(stripped)
        if image_match:
            flush_paragraph()
            add_figure(doc, image_match.group(2), image_match.group(1))
            index += 1
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            code_lines = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            add_code(doc, code_lines)
            index += 1
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            p = doc.add_paragraph(style=HEADING_STYLES[level])
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(heading.group(2))
            replace_run_properties(run, template_heading_rpr)
            index += 1
            continue
        if stripped.startswith("|") and index + 1 < len(lines) and lines[index + 1].strip().startswith("|"):
            flush_paragraph()
            table_rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_rows.append(parse_table_row(lines[index]))
                index += 1
            add_markdown_table(doc, table_rows)
            continue
        if stripped.startswith("> "):
            flush_paragraph()
            add_quote(doc, stripped[2:])
            index += 1
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            add_list_item(doc, stripped[2:])
            index += 1
            continue
        numbered = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if numbered:
            flush_paragraph()
            add_list_item(doc, numbered.group(2), marker=f"{numbered.group(1)}.")
            index += 1
            continue
        paragraph_buffer.append(raw)
        index += 1
    flush_paragraph()


def set_update_fields(doc):
    settings = doc.settings._element
    update_fields = settings.find(qn("w:updateFields"))
    if update_fields is None:
        update_fields = OxmlElement("w:updateFields")
        settings.append(update_fields)
    update_fields.set(qn("w:val"), "true")


def prepare_template_document():
    """以学校模板为母版，不重画封面和开头表格。"""
    doc = Document(TEMPLATE)

    # 保存模板标题的原始字符属性，后续逐个标题复制。
    template_heading_rpr = deepcopy(doc.paragraphs[2].runs[0]._element.rPr)

    # 学校模板的第 3 段起是各章编写提示和删除说明，成品中不保留。
    # 封面标题、原表格以及表格后的评语注释均完整保留。
    for paragraph in list(doc.paragraphs)[2:]:
        paragraph._element.getparent().remove(paragraph._element)

    # 仅在原有空白单元格中填写项目名称，不改变合并、列宽、行高和边框。
    table = doc.tables[0]
    project_paragraph = table.cell(0, 1).paragraphs[0]
    project_run = project_paragraph.add_run(PROJECT_NAME)
    table_text_rpr = table.cell(0, 0).paragraphs[0].runs[0]._element.rPr
    replace_run_properties(project_run, table_text_rpr)

    # 模板原页脚是右对齐，按报告统一要求仅调整页眉页脚对齐方式。
    for paragraph in doc.sections[0].header.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for paragraph in doc.sections[0].footer.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    return doc, template_heading_rpr


def build_report():
    doc, template_heading_rpr = prepare_template_document()
    configure_styles(doc, template_heading_rpr)

    body_section = doc.add_section(WD_SECTION.NEW_PAGE)
    configure_page(body_section, body=True)
    render_markdown(doc, SOURCE.read_text(encoding="utf-8"), template_heading_rpr)
    set_update_fields(doc)

    core = doc.core_properties
    core.title = PROJECT_NAME + "设计实践报告"
    core.subject = "大型程序设计实践"
    core.author = "课程学习助手 Agent 平台项目组"
    core.keywords = "课程学习助手, Agent, RAG, FastAPI, Vue"
    core.comments = "由项目实际代码、测试与课程原始需求整理。"

    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build_report()
