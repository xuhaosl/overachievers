import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildQuestionForm,
  buildQuestionOptions,
  normalizeNo,
  questionOptionLabel,
  selectWrongQuestions,
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
