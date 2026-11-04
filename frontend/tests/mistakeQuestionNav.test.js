import test from 'node:test'
import assert from 'node:assert/strict'

import {
  attachToNearestGroup,
  buildGroupAggregate,
  buildQuestionForm,
  buildQuestionOptions,
  groupSiblings,
  normalizeNo,
  questionOptionLabel,
  selectWrongQuestions,
  sortQuestionsByNo,
} from '../src/utils/mistakeQuestionNav.js'

test('题号下拉：优先显示识别到的小题号', () => {
  assert.equal(questionOptionLabel({ no: '2' }, 0), '第 2 题')
  assert.equal(questionOptionLabel({ no: '(3)' }, 5), '第 (3) 题')
})

test('题号下拉：没有题号时按顺序显示第几道', () => {
  assert.equal(questionOptionLabel({}, 0), '第 1 道')
  assert.equal(questionOptionLabel({ no: '' }, 2), '第 3 道')
  assert.equal(questionOptionLabel(null, 1), '第 2 道')
})

test('题号下拉：已处理的题带标记', () => {
  assert.equal(questionOptionLabel({ no: '1', done: true }, 0), '第 1 题（已处理）')
  assert.equal(questionOptionLabel({ done: true }, 3), '第 4 道（已处理）')
})

test('题号下拉：选项按识别顺序生成，value 对应 items 下标', () => {
  const items = [{ no: '2' }, { no: '' }, { no: '3', done: true }]
  assert.deepEqual(buildQuestionOptions(items), [
    { value: 0, label: '第 2 题' },
    { value: 1, label: '第 2 道' },
    { value: 2, label: '第 3 题（已处理）' },
  ])
  assert.deepEqual(buildQuestionOptions(), [])
})

test('题号下拉切换：选中下标后表单加载对应小题', () => {
  const items = [
    { no: '1', stem: '第一小题题干', my_answer: '甲' },
    { no: '2', stem: '第二小题题干', my_answer: '乙' },
    { no: '3', stem: '第三小题题干', my_answer: '丙' },
  ]
  const options = buildQuestionOptions(items)

  const selected = options[2].value
  const form = buildQuestionForm(items[selected], [9])

  assert.equal(selected, 2)
  assert.equal(form.no, '3')
  assert.equal(form.stem, '第三小题题干')
  assert.equal(form.my_answer, '丙')
  assert.deepEqual(form.set_ids, [9])
})

test('题号下拉切换：切到另一小题时不会残留上一题内容', () => {
  const first = buildQuestionForm({ no: '1', stem: '第一题', reason: '粗心' })
  const second = buildQuestionForm({ no: '2', stem: '第二题' })

  assert.equal(first.stem, '第一题')
  assert.equal(first.reason, '粗心')
  assert.equal(second.stem, '第二题')
  assert.equal(second.reason, '')
})

test('表单映射：知识点合并为顿号标签，缺省字段为空', () => {
  const form = buildQuestionForm({
    no: '4',
    stem: '阅读题小题',
    knowledge: ['概括内容', '理解主旨'],
    unit_ids: [3, 5],
  })

  assert.equal(form.knowledge_tags, '概括内容、理解主旨')
  assert.deepEqual(form.unit_ids, [3, 5])
  assert.equal(form.correct_answer, '')
  assert.equal(form.explanation, '')
})

test('表单映射：默认错题集为空时也返回空数组', () => {
  assert.deepEqual(buildQuestionForm().set_ids, [])
  assert.deepEqual(buildQuestionForm({}, null).set_ids, [])
})

test('批改痕迹：5 道小题只保留判错的 3 道，答对的不进入下拉', () => {
  const items = [
    { no: '1', is_wrong: false },
    { no: '2', is_wrong: true },
    { no: '3', is_wrong: false },
    { no: '4', is_wrong: true },
    { no: '5', is_wrong: true },
  ]

  const wrong = selectWrongQuestions(items, true)

  assert.deepEqual(wrong.map((q) => q.no), ['2', '4', '5'])
  assert.deepEqual(buildQuestionOptions(wrong).map((o) => o.label), ['第 2 题', '第 4 题', '第 5 题'])
})

test('批改痕迹：整道大题全对时返回空数组', () => {
  const items = [{ is_wrong: false }, { is_wrong: false }]
  assert.deepEqual(selectWrongQuestions(items, true), [])
})

test('批改痕迹：模型没标注 is_wrong 时返回 null，交给用户手动勾选', () => {
  const items = [{ no: '1' }, { no: '2' }]
  assert.equal(selectWrongQuestions(items, true), null)
})

test('没有批改痕迹：不自动过滤，保留全部供勾选', () => {
  const items = [{ no: '1', is_wrong: false }, { no: '2', is_wrong: true }]
  assert.deepEqual(selectWrongQuestions(items, false), items)
})

test('手动添加：题号归一化后可用于查重', () => {
  assert.equal(normalizeNo('第3题'), '3')
  assert.equal(normalizeNo('(2)'), '2')
  assert.equal(normalizeNo(' 4. '), '4')
  assert.equal(normalizeNo(''), '')
})

test('手动添加：按题号顺序排列，而不是追加到末尾', () => {
  const items = [{ no: '1' }, { no: '3' }, { no: '5' }, { no: '2' }]
  assert.deepEqual(sortQuestionsByNo(items).map((q) => q.no), ['1', '2', '3', '5'])
})

test('手动添加：(3) 按数字排序，无题号的题排最后', () => {
  const items = [{ no: '(4)' }, { no: '' }, { no: '2' }, { no: '第3题' }]
  assert.deepEqual(sortQuestionsByNo(items).map((q) => q.no), ['2', '第3题', '(4)', ''])
})

test('手动添加：题号相同时保持原有顺序', () => {
  const items = [{ no: '2', stem: '甲' }, { no: '(2)', stem: '乙' }, { no: '1', stem: '丙' }]
  assert.deepEqual(sortQuestionsByNo(items).map((q) => q.stem), ['丙', '甲', '乙'])
})

test('整体保存：同一大题下的错题归为一组', () => {
  const items = [
    { no: '1', group_no: '二', group_stem: '阅读材料', stem: '小题1' },
    { no: '2', group_no: '二', group_stem: '阅读材料', stem: '小题2' },
    { no: '3', group_no: '三', group_stem: '其他材料', stem: '小题3' },
  ]
  assert.deepEqual(groupSiblings(items, 0).map((q) => q.no), ['1', '2'])
  assert.deepEqual(groupSiblings(items, 2).map((q) => q.no), ['3'])
})

test('整体保存：题干保留公共材料，答案按小题合并', () => {
  const items = [
    {
      no: '1',
      group_no: '二',
      group_stem: '阅读材料',
      stem: '第一小题',
      my_answer: '甲答案',
      correct_answer: '甲标准',
      explanation: '甲解析',
      reason: '甲错因',
      knowledge: ['概括'],
    },
    {
      no: '3',
      group_no: '二',
      group_stem: '阅读材料',
      stem: '第三小题',
      my_answer: '丙答案',
      correct_answer: '丙标准',
      explanation: '丙解析',
      reason: '丙错因',
      knowledge: ['赏析'],
    },
  ]
  const merged = buildGroupAggregate(items, 0)
  assert.equal(merged.question_no, '二')
  assert.equal(merged.stem, '阅读材料\n\n（1）第一小题\n\n（3）第三小题')
  assert.equal(merged.my_answer, '（1）甲答案\n（3）丙答案')
  assert.equal(merged.correct_answer, '（1）甲标准\n（3）丙标准')
  assert.deepEqual(merged.knowledge, ['概括', '赏析'])
})

test('整体保存：有公共材料但只错一道小题时也保留材料', () => {
  const items = [
    {
      no: '2',
      group_no: '二',
      group_stem: '阅读材料',
      stem: '第二小题',
      my_answer: '乙答案',
      correct_answer: '乙标准',
    },
  ]
  const merged = buildGroupAggregate(items, 0)
  assert.ok(merged)
  assert.equal(merged.stem, '阅读材料\n\n（2）第二小题')
})

test('整体保存：group_no 不一致但公共材料相同也归为一组', () => {
  const items = [
    { no: '1', group_no: '1', group_stem: '同一段阅读材料', stem: '小题1' },
    { no: '2', group_no: '2', group_stem: '同一段阅读材料', stem: '小题2' },
    { no: '3', group_no: '3', stem: '独立题' },
  ]
  assert.deepEqual(groupSiblings(items, 0).map((q) => q.no), ['1', '2'])
  assert.deepEqual(groupSiblings(items, 2).map((q) => q.no), ['3'])
})

test('整体保存：只有部分小题填了公共材料时按大题号补全分组', () => {
  const items = [
    { no: '1', group_no: '二', group_stem: '阅读材料', stem: '小题1' },
    { no: '2', group_no: '二', group_stem: '', stem: '小题2' },
  ]
  assert.deepEqual(groupSiblings(items, 1).map((q) => q.no), ['1', '2'])
})

test('整体保存：合并记录使用 AI 生成的大题标题', () => {
  const items = [
    { no: '3', group_no: '二', group_title: '阅读理解《故乡》', group_stem: '阅读材料', stem: '3.人物形象' },
    { no: '4', group_no: '二', group_title: '阅读理解《故乡》', group_stem: '阅读材料', stem: '4.句子赏析' },
  ]
  assert.equal(buildGroupAggregate(items, 0).title, '阅读理解《故乡》')
})

test('手动补题：没有分组信息时并入已有大题', () => {
  const items = [
    { no: '3', group_no: '二', group_title: '阅读理解《故乡》', group_stem: '材料', stem: '第三小题' },
    { no: '4', group_no: '二', group_title: '阅读理解《故乡》', group_stem: '材料', stem: '第四小题' },
  ]
  const added = attachToNearestGroup({ no: '5', stem: '第五小题' }, items)
  assert.equal(added.group_no, '二')
  assert.equal(added.group_stem, '材料')
  assert.equal(added.group_title, '阅读理解《故乡》')
})

test('手动补题：已有分组信息且匹配时不覆盖', () => {
  const items = [{ no: '3', group_no: '二', group_stem: '材料' }]
  const added = attachToNearestGroup({ no: '4', group_no: '二', group_stem: '材料' }, items)
  assert.equal(added.group_no, '二')
})

test('手动补题：多个大题时并入题号最接近的一个', () => {
  const items = [
    { no: '3', group_no: '二', group_stem: '阅读材料' },
    { no: '4', group_no: '二', group_stem: '阅读材料' },
    { no: '9', group_no: '三', group_stem: '古诗材料' },
  ]
  const added = attachToNearestGroup({ no: '5', stem: '第五小题' }, items)
  assert.equal(added.group_no, '二')
})

test('手动补题：没有任何大题时不强行分组', () => {
  const added = attachToNearestGroup({ no: '5', stem: '独立题' }, [{ no: '1', stem: '第一题' }])
  assert.equal(added.group_no || '', '')
})

test('整体保存：独立题仍按单题保存', () => {
  const items = [{ no: '5', stem: '独立题', my_answer: '错', correct_answer: '对' }]
  assert.equal(buildGroupAggregate(items, 0), null)
})
