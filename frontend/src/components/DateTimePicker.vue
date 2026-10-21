<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  disabled?: boolean
  placeholder?: string
}>(), { placeholder: '选择日期与时间' })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const trigger = ref<HTMLButtonElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const opened = ref(false)
const positioned = ref(false)
const position = ref({ left: '0px', top: '0px' })
const selected = ref(new Date())
const month = ref(new Date())
const pad = (value: number) => String(value).padStart(2, '0')
const weekdays = ['一', '二', '三', '四', '五', '六', '日']
const hours = Array.from({ length: 24 }, (_, index) => index)
const minutes = Array.from({ length: 60 }, (_, index) => index)
const displayValue = computed(() => props.modelValue ? props.modelValue.replace('T', ' / ') : '')
const monthTitle = computed(() => `${month.value.getFullYear()} 年 ${month.value.getMonth() + 1} 月`)
const selectedDate = computed(() => `${selected.value.getMonth() + 1}月${selected.value.getDate()}日`)
const days = computed(() => {
  const start = new Date(month.value.getFullYear(), month.value.getMonth(), 1)
  start.setDate(1 - (start.getDay() + 6) % 7)
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start)
    date.setDate(start.getDate() + index)
    return date
  })
})
function sameDay(left: Date, right: Date) {
  return left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate()
}
function dateLabel(date: Date) {
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`
}
function placePanel() {
  if (!trigger.value || !panel.value) return
  const anchor = trigger.value.getBoundingClientRect()
  const rect = panel.value.getBoundingClientRect()
  const left = Math.max(12, Math.min(anchor.right - rect.width, window.innerWidth - rect.width - 12))
  const below = anchor.bottom + 10
  const top = below + rect.height <= window.innerHeight - 12
    ? below : Math.max(12, anchor.top - rect.height - 10)
  position.value = { left: `${left}px`, top: `${top}px` }
  positioned.value = true
}
function scrollSelectedTime() {
  panel.value?.querySelectorAll('.time-option.selected').forEach(element => {
    const option = element as HTMLElement
    const column = option.parentElement
    if (column) column.scrollTop = option.offsetTop - column.offsetTop - column.clientHeight / 2 + option.offsetHeight / 2
  })
}
async function open() {
  if (props.disabled || opened.value) return
  const parsed = props.modelValue ? new Date(props.modelValue) : new Date()
  selected.value = Number.isNaN(parsed.getTime()) ? new Date() : parsed
  selected.value.setSeconds(0, 0)
  month.value = new Date(selected.value.getFullYear(), selected.value.getMonth(), 1)
  opened.value = true
  positioned.value = false
  document.addEventListener('pointerdown', outside)
  window.addEventListener('resize', placePanel)
  window.addEventListener('scroll', placePanel, true)
  await nextTick()
  placePanel()
  scrollSelectedTime()
  panel.value?.focus()
}
function detach() {
  document.removeEventListener('pointerdown', outside)
  window.removeEventListener('resize', placePanel)
  window.removeEventListener('scroll', placePanel, true)
}
function close() {
  opened.value = false
  detach()
  trigger.value?.focus()
}
function outside(event: PointerEvent) {
  const target = event.target as Node
  if (!panel.value?.contains(target) && !trigger.value?.contains(target)) {
    opened.value = false
    detach()
  }
}
function shiftMonth(offset: number) {
  month.value = new Date(month.value.getFullYear(), month.value.getMonth() + offset, 1)
}
function chooseDay(date: Date) {
  const next = new Date(date)
  next.setHours(selected.value.getHours(), selected.value.getMinutes(), 0, 0)
  selected.value = next
  month.value = new Date(date.getFullYear(), date.getMonth(), 1)
}
function chooseHour(hour: number) {
  const next = new Date(selected.value)
  next.setHours(hour)
  selected.value = next
}
function commit(minute = selected.value.getMinutes()) {
  const date = new Date(selected.value)
  date.setMinutes(minute)
  emit('update:modelValue', `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`)
  close()
}
function clear() {
  emit('update:modelValue', '')
  close()
}
function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); close() }
  if (event.key !== 'Tab') return
  const buttons = panel.value?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')
  if (!buttons?.length) return
  const first = buttons[0], last = buttons[buttons.length - 1]
  if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.value)) {
    event.preventDefault(); last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first.focus()
  }
}
onBeforeUnmount(detach)
</script>

<template>
  <span class="date-time-picker">
    <button ref="trigger" type="button" class="date-trigger" :class="{ empty: !modelValue, open: opened }"
      :disabled="disabled" :aria-expanded="opened" aria-haspopup="dialog" aria-label="选择截止日期与时间"
      @click="opened ? close() : open()" @keydown.down.prevent="open">
      <span>{{ displayValue || placeholder }}</span>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="3.5" y="5" width="17" height="16" rx="3"/><path d="M7.5 3v4M16.5 3v4M3.5 10h17"/><path d="M8 14h2M14 14h2M8 17h2"/></svg>
    </button>
    <Teleport to="body">
      <section v-if="opened" ref="panel" class="date-panel" :style="{ ...position, visibility: positioned ? 'visible' : 'hidden' }"
        role="dialog" aria-label="选择截止日期与时间" tabindex="-1" @keydown="keydown">
        <header class="date-panel-header"><div><span>安排学习节奏</span><strong>选择截止时间</strong></div><button type="button" class="close-picker" aria-label="关闭时间选择器" @click="close">×</button></header>
        <div class="date-panel-body">
          <div class="calendar-section">
            <div class="month-navigation"><strong aria-live="polite">{{ monthTitle }}</strong><div><button type="button" aria-label="上个月" @click="shiftMonth(-1)">‹</button><button type="button" aria-label="下个月" @click="shiftMonth(1)">›</button></div></div>
            <div class="calendar-week"><span v-for="day in weekdays" :key="day">{{ day }}</span></div>
            <div class="calendar-days"><button v-for="day in days" :key="day.getTime()" type="button"
              :class="{ other: day.getMonth() !== month.getMonth(), selected: sameDay(day, selected), today: sameDay(day, new Date()) }"
              :aria-label="dateLabel(day)" :aria-pressed="sameDay(day, selected)" @click="chooseDay(day)">{{ day.getDate() }}</button></div>
            <button type="button" class="today-shortcut" @click="chooseDay(new Date())">回到今天</button>
          </div>
          <div class="time-section"><div class="time-head"><span>时</span><span>分</span></div><div class="time-columns">
            <div class="time-column" aria-label="选择小时"><button v-for="hour in hours" :key="hour" type="button" class="time-option" :class="{ selected: hour === selected.getHours() }" :aria-label="`${hour}时`" :aria-pressed="hour === selected.getHours()" @click="chooseHour(hour)">{{ pad(hour) }}</button></div>
            <div class="time-column" aria-label="选择分钟"><button v-for="minute in minutes" :key="minute" type="button" class="time-option" :class="{ selected: minute === selected.getMinutes() }" :aria-label="`${minute}分`" :aria-pressed="minute === selected.getMinutes()" @click="commit(minute)">{{ pad(minute) }}</button></div>
          </div></div>
        </div>
        <footer class="date-panel-footer"><span>{{ selectedDate }} <b>{{ pad(selected.getHours()) }}:{{ pad(selected.getMinutes()) }}</b><small>选好分钟后自动收起</small></span><div><button type="button" class="clear-date" @click="clear">清空</button><button type="button" class="confirm-date" @click="commit()">确定</button></div></footer>
      </section>
    </Teleport>
  </span>
</template>

<style scoped>
.date-time-picker{display:block;min-width:0;width:100%}.date-trigger{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;min-height:36px;padding:0 12px;border:1px solid #e1e6f6;border-radius:12px;background:#f7f9ff;color:#172052;font:inherit;text-align:left;transition:border-color .18s,box-shadow .18s}.date-trigger>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.date-trigger svg{flex-shrink:0;color:#8c98bc}.date-trigger.empty{color:#929cb4}.date-trigger:hover{border-color:#b8c1ee}.date-trigger.open,.date-trigger:focus-visible{outline:none;border-color:#8991ed;box-shadow:0 0 0 3px #707bf015}.date-trigger.open svg{color:#7478e9}
.date-panel{position:fixed;z-index:2000;width:min(430px,calc(100vw - 24px));max-height:calc(100dvh - 24px);overflow:auto;padding:20px;border:1px solid #e9eafa;border-radius:24px;background:linear-gradient(145deg,#fff 70%,#f7f6ff);box-shadow:0 18px 64px #303d8024,0 3px 12px #303d800a;color:#25305a;font:12px "Microsoft YaHei",system-ui,sans-serif;outline:none}.date-panel button{font:inherit;cursor:pointer}.date-panel button:focus-visible{outline:2px solid #7a79eb;outline-offset:2px}.date-panel-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}.date-panel-header>div{display:grid;gap:5px}.date-panel-header span{font-size:10px;letter-spacing:.08em;color:#929dc0}.date-panel-header strong{font-size:16px}.close-picker{width:28px;height:28px;border:0;border-radius:9px;background:#f2f4fb;color:#929bb5;font-size:20px!important}.date-panel-body{display:grid;grid-template-columns:minmax(0,1fr) 110px;gap:18px}.calendar-section{min-width:0}.month-navigation{display:flex;align-items:center;justify-content:space-between;height:28px;margin-bottom:12px}.month-navigation strong{font-size:12px;font-weight:600}.month-navigation>div{display:flex;gap:4px}.month-navigation button{width:24px;height:24px;padding:0;border:0;border-radius:8px;background:#f2f4fc;color:#7885af;font-size:19px}.calendar-week,.calendar-days{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:3px}.calendar-week{margin-bottom:7px;color:#a0a9c2;font-size:10px;text-align:center}.calendar-week span{padding:5px 0}.calendar-days button{position:relative;min-width:0;height:29px;border:0;border-radius:9px;background:transparent;color:#5f6c92;font-size:11px}.calendar-days button.other{color:#c6cbdc}.calendar-days button:hover{background:#eef1ff}.calendar-days button.today:after{position:absolute;bottom:3px;left:calc(50% - 2px);width:4px;height:4px;border-radius:50%;background:#7783e9;content:''}.calendar-days button.selected{background:linear-gradient(140deg,#6e8cf5,#8774ec);color:#fff;box-shadow:0 3px 8px #7779e830}.calendar-days button.selected:after{background:#fff}.today-shortcut{margin-top:10px;padding:4px 0;border:0;background:transparent;color:#7b83c7;font-size:10px!important}.time-section{padding-left:14px;border-left:1px solid #eff0f8}.time-head{display:grid;grid-template-columns:1fr 1fr;gap:6px;height:28px;margin-bottom:12px;align-items:center;color:#9ca6c2;font-size:10px;text-align:center}.time-columns{display:grid;grid-template-columns:1fr 1fr;gap:6px}.time-column{height:228px;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#dce0f3 transparent}.time-option{display:block;width:100%;height:30px;margin:2px 0;border:0;border-radius:9px;background:transparent;color:#7d89ab;font-size:11px!important;font-variant-numeric:tabular-nums}.time-option:hover{background:#f0f2fc}.time-option.selected{background:#eeecff;color:#7b6bd6;font-weight:700}.date-panel-footer{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:14px;padding-top:14px;border-top:1px solid #eff0f8}.date-panel-footer>span{color:#8793b0;font-size:10px}.date-panel-footer b{margin-left:5px;color:#6573ae;font-weight:600}.date-panel-footer small{display:block;margin-top:5px;font-size:9px;color:#abb2c8}.date-panel-footer>div{display:flex;gap:7px}.date-panel-footer button{height:30px;padding:0 12px;border:0;border-radius:10px;font-size:11px}.clear-date{background:transparent;color:#929db8}.confirm-date{background:linear-gradient(110deg,#5dcddd,#8276ed);color:#fff}
@media(max-width:400px){.date-panel{padding:16px}.date-panel-body{grid-template-columns:minmax(0,1fr) 90px;gap:10px}.time-section{padding-left:10px}.calendar-days{gap:1px}.date-panel-footer button{padding:0 9px}}
</style>
