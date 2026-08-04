import {
  Button,
  Checkbox,
  Codicon,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  EmptyState,
  ErrorState,
  GlyphSpinner,
  Input,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  SearchField,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  SegmentedControl,
  cn,
  haptic,
  host,
  useMutation,
  useQuery,
  useQueryClient
} from '@hermes/plugin-sdk'
import { useEffect, useMemo, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'tasks'
const QUERY_KEY = [ID, 'board']
const SECTION_ORDER = ['Next', 'Doing', 'Waiting', 'Done']
const LATER_SECTION = 'Later'
const ALL_SECTIONS = [...SECTION_ORDER, LATER_SECTION]
const VIEW_MODES = [
  { id: 'live', label: 'Live' },
  { id: 'demo', label: 'Demo' }
]
const SECTION_COPY = {
  Next: { description: 'Committed next actions', icon: 'arrow-right' },
  Doing: { description: 'In progress', icon: 'pulse' },
  Waiting: { description: 'Blocked or delegated', icon: 'clock' },
  Done: { description: 'Recently completed', icon: 'check-all' },
  Later: { description: 'Uncommitted options', icon: 'archive' }
}
const DEMO_TASKS = [
  { id: 'demo-01', title: 'Ship Tasks V2', section: 'Doing', area: 'creative', priority: true },
  { id: 'demo-02', title: 'Review the release checklist', section: 'Doing', area: 'work', priority: false },
  { id: 'demo-03', title: 'Record a short click-through', section: 'Next', area: 'creative', priority: true },
  { id: 'demo-04', title: 'Write the GitHub release notes', section: 'Next', area: 'work', priority: false },
  { id: 'demo-05', title: 'Book the dentist appointment', section: 'Next', area: 'life', priority: false },
  { id: 'demo-06', title: 'Confirm feedback from the tester', section: 'Waiting', area: 'work', priority: false },
  { id: 'demo-07', title: 'Wait for the icon export', section: 'Waiting', area: 'creative', priority: false },
  { id: 'demo-08', title: 'Explore a weekly review', section: 'Later', area: 'life', priority: false },
  { id: 'demo-09', title: 'Add keyboard shortcuts', section: 'Later', area: 'creative', priority: false },
  { id: 'demo-10', title: 'Choose the personal workflow', section: 'Done', area: 'life', priority: false, done: true, completed_at: '2026-08-03' },
  { id: 'demo-11', title: 'Keep tasks.md as the source of truth', section: 'Done', area: 'work', priority: true, done: true, completed_at: '2026-08-03' },
  { id: 'demo-12', title: 'Build the atomic mutation backend', section: 'Done', area: 'work', priority: false, done: true, completed_at: '2026-08-03' }
]
let pluginContext = null

function request(path, options) {
  if (!pluginContext) return Promise.reject(new Error('Tasks plugin is not ready'))
  return pluginContext.rest(path, options)
}

function emptySections() {
  return Object.fromEntries(ALL_SECTIONS.map(section => [section, []]))
}

function normalizeAreaName(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^[-_]+|[-_]+$/g, '')
}

function recalculateBoard(input) {
  const sections = emptySections()
  for (const section of ALL_SECTIONS) {
    sections[section] = [...(input.sections?.[section] || [])]
  }
  const tasks = ALL_SECTIONS.flatMap(section => sections[section])
  const doing = sections.Doing.filter(task => !task.done)
  const next = sections.Next.filter(task => !task.done)
  const firstPriority = list => list.find(task => task.priority) || list[0] || null
  const areas = [...new Set([...(input.areas || []), ...tasks.map(task => task.area).filter(Boolean)])]
  const doingLimit = input.doing_limit || 3
  return {
    ...input,
    sections,
    areas,
    doing_limit: doingLimit,
    counts: {
      open: tasks.filter(task => !task.done).length,
      priority: tasks.filter(task => !task.done && task.priority).length,
      done: tasks.filter(task => task.done).length
    },
    counts_by_section: Object.fromEntries(ALL_SECTIONS.map(section => [section, sections[section].length])),
    focus_task_id: firstPriority(doing)?.id || null,
    next_task_id: firstPriority(next)?.id || null,
    waiting_count: sections.Waiting.length,
    wip: { count: doing.length, limit: doingLimit, over_limit: doing.length > doingLimit }
  }
}

function createDemoBoard() {
  const sections = emptySections()
  for (const item of DEMO_TASKS) {
    sections[item.section].push({
      ...item,
      done: item.section === 'Done' || Boolean(item.done),
      completed_at: item.completed_at || null
    })
  }
  return recalculateBoard({
    sections,
    areas: ['work', 'life', 'creative'],
    doing_limit: 3,
    revision: 'demo'
  })
}

function updateBoardLocally(board, id, patch) {
  const sections = emptySections()
  let selected = null
  let sourcePosition = null
  for (const section of ALL_SECTIONS) {
    for (const [index, task] of (board.sections?.[section] || []).entries()) {
      if (task.id === id) {
        selected = task
        sourcePosition = index
      }
      else sections[section].push(task)
    }
  }
  if (!selected || patch.__delete) return recalculateBoard({ ...board, sections })
  const targetSection = patch.section || selected.section
  const next = {
    ...selected,
    ...patch,
    section: targetSection,
    done: targetSection === 'Done',
    completed_at: targetSection === 'Done' ? selected.completed_at || new Date().toISOString().slice(0, 10) : null
  }
  delete next.__delete
  delete next.position
  const targetPosition = Number.isInteger(patch.position)
    ? patch.position
    : targetSection === selected.section ? sourcePosition : null
  if (Number.isInteger(targetPosition)) {
    sections[targetSection].splice(Math.max(0, targetPosition), 0, next)
  } else {
    sections[targetSection].push(next)
  }
  return recalculateBoard({ ...board, sections })
}

function addBoardTask(board, task) {
  const sections = Object.fromEntries(ALL_SECTIONS.map(section => [section, [...(board.sections?.[section] || [])]]))
  sections[task.section].push(task)
  return recalculateBoard({ ...board, sections, areas: [...(board.areas || []), task.area].filter(Boolean) })
}

function createAreaLocally(board, name) {
  const area = normalizeAreaName(name)
  if (!area) throw new Error('Enter an area name')
  if (board.areas.includes(area)) throw new Error('That area already exists')
  return recalculateBoard({ ...board, areas: [...board.areas, area] })
}

function renameAreaLocally(board, area, name) {
  const nextArea = normalizeAreaName(name)
  if (!nextArea) throw new Error('Enter an area name')
  if (!board.areas.includes(area)) throw new Error('That area no longer exists')
  if (nextArea !== area && board.areas.includes(nextArea)) throw new Error('That area already exists')
  const sections = Object.fromEntries(ALL_SECTIONS.map(section => [
    section,
    (board.sections[section] || []).map(task => task.area === area ? { ...task, area: nextArea } : task)
  ]))
  return recalculateBoard({
    ...board,
    sections,
    areas: board.areas.map(item => item === area ? nextArea : item)
  })
}

function removeAreaLocally(board, area, replacement = null) {
  if (!board.areas.includes(area)) throw new Error('That area no longer exists')
  if (replacement && (!board.areas.includes(replacement) || replacement === area)) {
    throw new Error('Choose a different existing replacement area')
  }
  const sections = Object.fromEntries(ALL_SECTIONS.map(section => [
    section,
    (board.sections[section] || []).map(task => task.area === area ? { ...task, area: replacement || null } : task)
  ]))
  return recalculateBoard({
    ...board,
    sections,
    areas: board.areas.filter(item => item !== area)
  })
}

function dropPosition(canonicalTasks, draggedId, targetId) {
  const sourcePosition = canonicalTasks.findIndex(task => task.id === draggedId)
  const targetPosition = canonicalTasks.findIndex(task => task.id === targetId)
  return sourcePosition >= 0 && sourcePosition < targetPosition
    ? targetPosition - 1
    : targetPosition
}

function useBoard(refetchInterval = 3000) {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => request('/board'),
    refetchInterval,
    staleTime: 900,
    retry: 2
  })
}

function Count({ label, value, strong = false }) {
  return jsxs('div', {
    className: 'flex items-baseline gap-1',
    children: [
      jsx('span', {
        className: cn('text-sm tabular-nums', strong ? 'font-semibold text-foreground' : 'text-(--ui-text-secondary)'),
        children: value
      }),
      jsx('span', { className: 'text-[0.6875rem] text-(--ui-text-quaternary)', children: label })
    ]
  })
}

function AreaFilters({ areas, value, onChange }) {
  const choices = [{ id: 'all', label: 'All' }, { id: 'priority', label: 'Priority' }, ...areas.map(area => ({ id: area, label: area }))]
  return jsx('div', {
    className: 'flex min-w-0 flex-wrap items-center gap-1',
    children: choices.map(choice =>
      jsx(Button, {
        'aria-pressed': value === choice.id,
        className: 'capitalize',
        onClick: () => onChange(choice.id),
        size: 'xs',
        type: 'button',
        variant: value === choice.id ? 'secondary' : 'ghost',
        children: choice.label
      }, choice.id)
    )
  })
}

function AreaManager({ areas, board, busy, onClose, onCreate, onRemove, onRename, open }) {
  const [name, setName] = useState('')
  const [editing, setEditing] = useState(null)
  const [removing, setRemoving] = useState(null)
  const [replacement, setReplacement] = useState('__none__')
  const [clearArmed, setClearArmed] = useState(false)
  const counts = Object.fromEntries(areas.map(area => [
    area,
    ALL_SECTIONS.flatMap(section => board.sections[section] || []).filter(task => task.area === area).length
  ]))

  const close = () => {
    setName('')
    setEditing(null)
    setRemoving(null)
    setReplacement('__none__')
    setClearArmed(false)
    onClose()
  }

  return jsx(Dialog, {
    open,
    onOpenChange: nextOpen => { if (!nextOpen) close() },
    children: jsxs(DialogContent, {
      className: 'max-w-md',
      children: [
        jsx(DialogHeader, {
          children: [
            jsx(DialogTitle, { children: 'Manage areas' }),
            jsx(DialogDescription, { children: 'Areas group tasks without changing their workflow status.' })
          ]
        }),
        jsxs('form', {
          className: 'flex gap-2',
          onSubmit: async event => {
            event.preventDefault()
            if (!name.trim() || busy) return
            const saved = editing ? await onRename(editing, name) : await onCreate(name)
            if (saved) {
              setName('')
              setEditing(null)
            }
          },
          children: [
            jsx(Input, {
              'aria-label': editing ? `Rename ${editing}` : 'New area name',
              disabled: busy,
              onChange: event => setName(event.target.value),
              placeholder: editing ? `Rename ${editing}` : 'New area',
              value: name
            }),
            editing ? jsx(Button, {
              disabled: busy,
              onClick: () => { setEditing(null); setName('') },
              size: 'sm',
              type: 'button',
              variant: 'ghost',
              children: 'Cancel'
            }) : null,
            jsx(Button, {
              disabled: busy || !name.trim(),
              size: 'sm',
              type: 'submit',
              children: busy ? jsx(GlyphSpinner, { className: 'size-3.5' }) : editing ? 'Rename' : 'Add'
            })
          ]
        }),
        jsx('div', {
          className: 'max-h-72 space-y-1 overflow-y-auto',
          children: areas.length ? areas.map(area => jsxs('div', {
            className: 'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-secondary) px-3 py-2',
            children: [
              jsxs('div', {
                className: 'flex items-center gap-2',
                children: [
                  jsx('span', { className: 'min-w-0 flex-1 truncate text-xs font-medium capitalize', children: area.replaceAll('-', ' ') }),
                  jsx('span', { className: 'text-[0.625rem] tabular-nums text-(--ui-text-quaternary)', children: `${counts[area]} tasks` }),
                  jsx(Button, {
                    disabled: busy,
                    onClick: () => { setEditing(area); setRemoving(null); setClearArmed(false); setName(area) },
                    size: 'xs',
                    type: 'button',
                    variant: 'ghost',
                    children: 'Rename'
                  }),
                  jsx(Button, {
                    disabled: busy,
                    onClick: () => { setRemoving(area); setEditing(null); setReplacement('__none__'); setClearArmed(false) },
                    size: 'xs',
                    type: 'button',
                    variant: 'ghost',
                    children: 'Remove'
                  })
                ]
              }),
              removing === area ? jsxs('div', {
                className: 'mt-2 flex flex-wrap items-center gap-2 border-t border-(--ui-stroke-secondary) pt-2',
                children: [
                  jsx('span', {
                    className: 'min-w-32 flex-1 text-[0.6875rem] text-(--ui-text-tertiary)',
                    children: counts[area] ? `Reassign ${counts[area]} affected tasks:` : 'This area has no tasks.'
                  }),
                  counts[area] ? jsx(Select, {
                    onValueChange: value => { setReplacement(value); setClearArmed(false) },
                    value: replacement,
                    children: [
                      jsx(SelectTrigger, {
                        'aria-label': `Replacement for ${area}`,
                        className: 'w-32',
                        children: jsx(SelectValue, {})
                      }),
                      jsx(SelectContent, {
                        children: [
                          jsx(SelectItem, { value: '__none__', children: 'No area' }),
                          ...areas.filter(option => option !== area).map(option => jsx(SelectItem, {
                            value: option,
                            children: option.replaceAll('-', ' ')
                          }, option))
                        ]
                      })
                    ]
                  }) : null,
                  clearArmed ? jsx('span', {
                    className: 'w-full text-[0.6875rem] text-(--ui-danger)',
                    children: 'This permanently clears the area label from every affected task. The tasks themselves are kept.'
                  }) : null,
                  jsx(Button, {
                    disabled: busy,
                    onClick: async () => {
                      if (counts[area] && replacement === '__none__' && !clearArmed) {
                        setClearArmed(true)
                        return
                      }
                      const saved = await onRemove(area, replacement === '__none__' ? null : replacement)
                      if (saved) {
                        setRemoving(null)
                        setClearArmed(false)
                      }
                    },
                    size: 'sm',
                    type: 'button',
                    variant: 'destructive',
                    children: busy
                      ? jsx(GlyphSpinner, { className: 'size-3.5' })
                      : clearArmed ? 'Confirm clear & remove' : 'Remove area'
                  }),
                  jsx(Button, {
                    disabled: busy,
                    onClick: () => { setRemoving(null); setClearArmed(false) },
                    size: 'sm',
                    type: 'button',
                    variant: 'ghost',
                    children: 'Cancel'
                  })
                ]
              }) : null
            ]
          }, area)) : jsx(EmptyState, {
            title: 'No areas',
            description: 'Add one when you need another part of life.'
          })
        }),
        jsx(DialogFooter, {
          children: jsx(Button, { onClick: close, size: 'sm', type: 'button', variant: 'ghost', children: 'Done' })
        })
      ]
    })
  })
}

function TaskCard({ task, pending, onComplete, onOpen }) {
  return jsxs('article', {
    className: cn(
      'group rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-primary) px-3 py-2.5 shadow-sm transition-[border-color,opacity,transform]',
      'hover:border-(--ui-stroke-primary)',
      task.priority && 'border-l-2 border-l-(--ui-accent)',
      pending && 'pointer-events-none opacity-55'
    ),
    draggable: task.section !== 'Done',
    onDragStart: event => {
      event.dataTransfer.effectAllowed = 'move'
      event.dataTransfer.setData('text/plain', task.id)
    },
    children: [
      jsxs('div', {
        className: 'flex items-start gap-2.5',
        children: [
          jsx(Checkbox, {
            'aria-label': task.done ? `Reopen ${task.title}` : `Complete ${task.title}`,
            checked: task.done,
            className: 'mt-0.5 shrink-0',
            disabled: pending,
            onCheckedChange: checked => onComplete(task, checked === true)
          }),
          jsxs('button', {
            className: 'min-w-0 flex-1 text-left',
            onClick: () => onOpen(task),
            type: 'button',
            children: [
              jsx('span', {
                className: cn(
                  'block overflow-hidden text-ellipsis text-[0.8125rem] leading-5 text-foreground',
                  task.done && 'text-(--ui-text-quaternary) line-through'
                ),
                children: task.title
              }),
              jsxs('span', {
                className: 'mt-1 flex items-center gap-2 text-[0.625rem] uppercase tracking-wide text-(--ui-text-quaternary)',
                children: [
                  task.area ? jsx('span', { className: 'capitalize', children: task.area }) : null,
                  task.priority ? jsxs('span', {
                    className: 'inline-flex items-center gap-1 text-(--ui-accent)',
                    children: [jsx(Codicon, { name: 'flame', size: '0.6875rem' }), 'priority']
                  }) : null,
                  task.completed_at ? jsx('span', { children: task.completed_at }) : null
                ]
              })
            ]
          }),
          pending ? jsx(GlyphSpinner, { className: 'mt-1 size-3.5 shrink-0' }) : jsx(Button, {
            'aria-label': `Edit ${task.title}`,
            className: 'shrink-0 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 focus:opacity-100',
            onClick: () => onOpen(task),
            size: 'icon-xs',
            type: 'button',
            variant: 'ghost',
            children: jsx(Codicon, { name: 'ellipsis', size: '0.875rem' })
          })
        ]
      })
    ]
  })
}

function BoardColumn({ section, tasks, canonicalTasks, collapsed, doingLimit, dragOver, pendingId, onAddHere, onComplete, onDropTask, onOpen, onSetDragOver, onToggleCollapsed }) {
  const copy = SECTION_COPY[section]
  const overLimit = section === 'Doing' && tasks.length > doingLimit
  const shown = section === 'Done' ? [...tasks].reverse().slice(0, 10) : tasks
  if (collapsed) {
    return jsx('button', {
      'aria-expanded': false,
      'aria-label': `Expand ${section}`,
      className: cn(
        'flex h-full min-h-0 w-12 shrink-0 flex-col items-center gap-2 rounded-xl border border-(--ui-stroke-secondary) bg-(--ui-bg-secondary) py-3 text-(--ui-text-tertiary) transition-[width,border-color,background-color]',
        'hover:border-(--ui-stroke-primary) hover:text-foreground',
        dragOver && 'border-(--ui-accent) bg-(--ui-accent)/5'
      ),
      onClick: () => onToggleCollapsed(section),
      onDragEnter: event => {
        event.preventDefault()
        onSetDragOver(section)
      },
      onDragOver: event => {
        event.preventDefault()
        event.dataTransfer.dropEffect = 'move'
      },
      onDragLeave: event => {
        if (!event.currentTarget.contains(event.relatedTarget)) onSetDragOver(null)
      },
      onDrop: event => {
        event.preventDefault()
        event.stopPropagation()
        const taskId = event.dataTransfer.getData('text/plain')
        onSetDragOver(null)
        if (taskId) onDropTask(taskId, section)
      },
      title: `Expand ${section}`,
      type: 'button',
      children: [
        jsx(Codicon, { name: copy.icon, size: '0.875rem' }),
        jsx('span', {
          className: '[writing-mode:vertical-rl] text-[0.6875rem] font-medium tracking-wide',
          children: section
        }),
        jsx('span', { className: 'text-[0.625rem] tabular-nums text-(--ui-text-quaternary)', children: tasks.length })
      ]
    })
  }
  return jsxs('section', {
    className: cn(
      'flex h-full min-h-0 shrink-0 flex-col rounded-xl border border-(--ui-stroke-secondary) bg-(--ui-bg-secondary)',
      section === 'Doing' ? 'w-80' : section === 'Done' ? 'w-60' : 'w-72',
      dragOver && 'border-(--ui-accent) bg-(--ui-accent)/5'
    ),
    onDragEnter: event => {
      event.preventDefault()
      onSetDragOver(section)
    },
    onDragOver: event => {
      event.preventDefault()
      event.dataTransfer.dropEffect = 'move'
    },
    onDragLeave: event => {
      if (!event.currentTarget.contains(event.relatedTarget)) onSetDragOver(null)
    },
    onDrop: event => {
      event.preventDefault()
      const taskId = event.dataTransfer.getData('text/plain')
      onSetDragOver(null)
      if (taskId) onDropTask(taskId, section)
    },
    children: [
      jsxs('header', {
        className: 'flex shrink-0 items-start gap-2 border-b border-(--ui-stroke-secondary) px-3 py-3',
        children: [
          jsx(Codicon, { className: 'mt-0.5 text-(--ui-text-tertiary)', name: copy.icon, size: '0.875rem' }),
          jsxs('div', {
            className: 'min-w-0 flex-1',
            children: [
              jsxs('div', {
                className: 'flex items-center gap-2',
                children: [
                  jsx('h2', { className: 'text-xs font-semibold text-foreground', children: section }),
                  jsx('span', { className: 'text-[0.625rem] tabular-nums text-(--ui-text-quaternary)', children: tasks.length }),
                  overLimit ? jsx('span', {
                    className: 'rounded bg-(--ui-accent)/10 px-1.5 py-0.5 text-[0.625rem] font-medium text-(--ui-accent)',
                    children: `limit ${doingLimit}`
                  }) : null
                ]
              }),
              jsx('p', { className: 'mt-0.5 text-[0.625rem] text-(--ui-text-quaternary)', children: copy.description })
            ]
          }),
          jsx(Button, {
            'aria-expanded': true,
            'aria-label': `Collapse ${section}`,
            onClick: () => onToggleCollapsed(section),
            size: 'icon-xs',
            title: `Collapse ${section}`,
            type: 'button',
            variant: 'ghost',
            children: jsx(Codicon, { name: 'chevron-left', size: '0.875rem' })
          }),
          section !== 'Done' ? jsx(Button, {
            'aria-label': `Add task to ${section}`,
            onClick: () => onAddHere(section),
            size: 'icon-xs',
            type: 'button',
            variant: 'ghost',
            children: jsx(Codicon, { name: 'add', size: '0.875rem' })
          }) : null
        ]
      }),
      jsx('div', {
        className: 'min-h-0 flex-1 space-y-2 overflow-y-auto p-2',
        children: shown.length
          ? shown.map(task => jsx('div', {
              onDragOver: event => {
                event.preventDefault()
              },
              onDrop: event => {
                event.preventDefault()
                event.stopPropagation()
                const taskId = event.dataTransfer.getData('text/plain')
                onSetDragOver(null)
                if (taskId) {
                  const position = dropPosition(canonicalTasks, taskId, task.id)
                  onDropTask(
                    taskId,
                    section,
                    section === 'Done' ? {} : { position }
                  )
                }
              },
              children: jsx(TaskCard, {
                task,
                pending: pendingId === task.id,
                onComplete,
                onOpen
              })
              }, task.id))
          : jsx('div', {
              className: 'flex h-24 items-center justify-center rounded-lg border border-dashed border-(--ui-stroke-secondary) text-[0.6875rem] text-(--ui-text-quaternary)',
              children: dragOver ? 'Drop here' : 'Clear'
            })
      })
    ]
  })
}

function TaskEditor({ draft, deleteArmed, pending, onAsk, onChange, onClose, onDelete, onSave, asking }) {
  if (!draft) return null
  return jsx(Dialog, {
    open: true,
    onOpenChange: open => { if (!open) onClose() },
    children: jsxs(DialogContent, {
      className: 'max-w-md',
      children: [
        jsx(DialogHeader, {
          children: [
            jsx(DialogTitle, { children: 'Task' }),
            jsx(DialogDescription, { children: 'Edit this personal task or explicitly ask Hermes for help.' })
          ]
        }),
        jsxs('div', {
          className: 'space-y-4 py-2',
          children: [
            jsxs('label', {
              className: 'block space-y-1.5',
              children: [
                jsx('span', { className: 'text-[0.6875rem] font-medium text-(--ui-text-secondary)', children: 'Title' }),
                jsx(Input, {
                  'aria-label': 'Task title',
                  autoFocus: true,
                  onChange: event => onChange({ ...draft, title: event.target.value }),
                  value: draft.title
                })
              ]
            }),
            jsxs('div', {
              className: 'grid grid-cols-2 gap-3',
              children: [
                jsxs('label', {
                  className: 'block space-y-1.5',
                  children: [
                    jsx('span', { className: 'text-[0.6875rem] font-medium text-(--ui-text-secondary)', children: 'Status' }),
                    jsx(Select, {
                      onValueChange: section => onChange({ ...draft, section }),
                      value: draft.section,
                      children: [
                        jsx(SelectTrigger, {
                          'aria-label': 'Task status',
                          children: jsx(SelectValue, {})
                        }),
                        jsx(SelectContent, {
                          children: ALL_SECTIONS.map(section => jsx(SelectItem, { value: section, children: section }, section))
                        })
                      ]
                    })
                  ]
                }),
                jsxs('label', {
                  className: 'block space-y-1.5',
                  children: [
                    jsx('span', { className: 'text-[0.6875rem] font-medium text-(--ui-text-secondary)', children: 'Area' }),
                    jsx(Input, {
                      'aria-label': 'Task area',
                      onChange: event => onChange({ ...draft, area: event.target.value }),
                      placeholder: 'Work, life, health…',
                      value: draft.area || ''
                    })
                  ]
                })
              ]
            }),
            jsxs('label', {
              className: 'flex items-center gap-2 text-xs text-(--ui-text-secondary)',
              children: [
                jsx(Checkbox, {
                  checked: Boolean(draft.priority),
                  onCheckedChange: checked => onChange({ ...draft, priority: checked === true })
                }),
                'Priority'
              ]
            })
          ]
        }),
        jsxs(DialogFooter, {
          className: 'flex-wrap justify-between gap-2 sm:justify-between',
          children: [
            jsxs('div', {
              className: 'flex gap-2',
              children: [
                jsx(Button, {
                  disabled: pending || asking,
                  onClick: () => onAsk(draft),
                  size: 'sm',
                  type: 'button',
                  variant: 'secondary',
                  children: asking ? jsx(GlyphSpinner, { className: 'size-3.5' }) : 'Ask Hermes'
                }),
                jsx(Button, {
                  disabled: pending,
                  onClick: onDelete,
                  size: 'sm',
                  type: 'button',
                  variant: deleteArmed ? 'destructive' : 'ghost',
                  children: deleteArmed ? 'Confirm delete' : 'Delete'
                })
              ]
            }),
            jsxs('div', {
              className: 'flex gap-2',
              children: [
                jsx(Button, { onClick: onClose, size: 'sm', type: 'button', variant: 'ghost', children: 'Cancel' }),
                jsx(Button, {
                  disabled: pending || !draft.title.trim(),
                  onClick: () => onSave(draft),
                  size: 'sm',
                  type: 'button',
                  children: pending ? jsx(GlyphSpinner, { className: 'size-3.5' }) : 'Save'
                })
              ]
            })
          ]
        })
      ]
    })
  })
}

function TasksPage() {
  const queryClient = useQueryClient()
  const boardQuery = useBoard()
  const addInputRef = useRef(null)
  const searchInputRef = useRef(null)
  const [mode, setMode] = useState('live')
  const [demoBoard, setDemoBoard] = useState(createDemoBoard)
  const [title, setTitle] = useState('')
  const [newArea, setNewArea] = useState('')
  const [newPriority, setNewPriority] = useState(false)
  const [addSection, setAddSection] = useState('Next')
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [areaManagerOpen, setAreaManagerOpen] = useState(false)
  const [collapsedSections, setCollapsedSections] = useState(() => new Set([LATER_SECTION]))
  const [dragOver, setDragOver] = useState(null)
  const [pendingId, setPendingId] = useState(null)
  const [draft, setDraft] = useState(null)
  const [deleteArmed, setDeleteArmed] = useState(false)
  const [asking, setAsking] = useState(false)

  useEffect(() => {
    const onKeyDown = event => {
      const target = event.target
      const editing = target instanceof HTMLElement && (
        target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
      )
      if (editing) return
      if (event.key === '/') {
        event.preventDefault()
        searchInputRef.current?.focus()
      } else if (event.key.toLowerCase() === 'n') {
        event.preventDefault()
        addInputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const liveBoard = boardQuery.data
  const board = mode === 'demo' ? demoBoard : liveBoard

  const toggleCollapsed = section => {
    setCollapsedSections(current => {
      const next = new Set(current)
      if (next.has(section)) next.delete(section)
      else next.add(section)
      return next
    })
  }

  const updateMutation = useMutation({
    mutationFn: ({ id, patch, revision }) => request(`/tasks/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: { ...patch, revision }
    }),
    onMutate: async ({ id, patch }) => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY })
      const previous = queryClient.getQueryData(QUERY_KEY)
      setPendingId(id)
      if (previous) queryClient.setQueryData(QUERY_KEY, updateBoardLocally(previous, id, patch))
      return { previous }
    },
    onSuccess: nextBoard => {
      queryClient.setQueryData(QUERY_KEY, nextBoard)
      setDraft(null)
      setDeleteArmed(false)
      haptic('success')
    },
    onError: (error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(QUERY_KEY, context.previous)
      host.notifyError(error, 'Task changed elsewhere — refreshed safely')
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onSettled: () => {
      setPendingId(null)
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    }
  })

  const addMutation = useMutation({
    mutationFn: payload => request('/tasks', { method: 'POST', body: payload }),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY })
    },
    onSuccess: nextBoard => {
      queryClient.setQueryData(QUERY_KEY, nextBoard)
      setTitle('')
      setNewPriority(false)
      haptic('success')
    },
    onError: error => {
      host.notifyError(error, 'Could not add task')
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    }
  })

  const deleteMutation = useMutation({
    mutationFn: ({ id, revision }) => request(`/tasks/${encodeURIComponent(id)}?revision=${encodeURIComponent(revision)}`, { method: 'DELETE' }),
    onMutate: async ({ id }) => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY })
      const previous = queryClient.getQueryData(QUERY_KEY)
      setPendingId(id)
      if (previous) queryClient.setQueryData(QUERY_KEY, updateBoardLocally(previous, id, { __delete: true }))
      return { previous }
    },
    onSuccess: nextBoard => {
      queryClient.setQueryData(QUERY_KEY, nextBoard)
      setDraft(null)
      setDeleteArmed(false)
      haptic('success')
    },
    onError: (error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(QUERY_KEY, context.previous)
      host.notifyError(error, 'Could not delete task')
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onSettled: () => {
      setPendingId(null)
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    }
  })

  const areaMutation = useMutation({
    mutationFn: operation => {
      if (operation.type === 'create') {
        return request('/areas', {
          method: 'POST',
          body: { name: operation.name, revision: operation.revision }
        })
      }
      if (operation.type === 'rename') {
        return request(`/areas/${encodeURIComponent(operation.area)}`, {
          method: 'PATCH',
          body: { name: operation.name, revision: operation.revision }
        })
      }
      const query = new URLSearchParams({ revision: operation.revision })
      if (operation.replacement) query.set('replacement', operation.replacement)
      return request(`/areas/${encodeURIComponent(operation.area)}?${query}`, { method: 'DELETE' })
    },
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY })
    },
    onSuccess: (nextBoard, operation) => {
      queryClient.setQueryData(QUERY_KEY, nextBoard)
      if (filter === operation.area) {
        setFilter(operation.type === 'rename'
          ? normalizeAreaName(operation.name)
          : operation.replacement || 'all')
      }
      haptic('success')
    },
    onError: error => {
      host.notifyError(error, 'Could not update areas')
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY })
  })

  const busy = updateMutation.isPending || addMutation.isPending || deleteMutation.isPending || areaMutation.isPending

  const mutateArea = async operation => {
    if (!board || busy) return false
    let requestStarted = false
    try {
      const nextBoard = operation.type === 'create'
        ? createAreaLocally(board, operation.name)
        : operation.type === 'rename'
          ? renameAreaLocally(board, operation.area, operation.name)
          : removeAreaLocally(board, operation.area, operation.replacement)
      if (mode === 'demo') {
        setDemoBoard(nextBoard)
        if (filter === operation.area) {
          setFilter(operation.type === 'rename'
            ? normalizeAreaName(operation.name)
            : operation.replacement || 'all')
        }
        haptic('success')
        return true
      }
      requestStarted = true
      await areaMutation.mutateAsync({ ...operation, revision: board.revision })
      return true
    } catch (error) {
      if (!requestStarted) host.notifyError(error, 'Could not update areas')
      return false
    }
  }

  const mutateTask = (id, patch) => {
    if (!board || busy) return
    if (mode === 'demo') {
      setDemoBoard(current => updateBoardLocally(current, id, patch))
      setDraft(null)
      setDeleteArmed(false)
      haptic('success')
      return
    }
    updateMutation.mutate({ id, patch, revision: board.revision })
  }

  const deleteTask = id => {
    if (!board || busy) return
    if (!deleteArmed) {
      setDeleteArmed(true)
      return
    }
    if (mode === 'demo') {
      setDemoBoard(current => updateBoardLocally(current, id, { __delete: true }))
      setDraft(null)
      setDeleteArmed(false)
      haptic('success')
      return
    }
    deleteMutation.mutate({ id, revision: board.revision })
  }

  const submit = event => {
    event.preventDefault()
    const clean = title.trim()
    if (!clean || !board || busy) return
    const area = normalizeAreaName(newArea)
    if (mode === 'demo') {
      const task = {
        id: `demo-user-${Date.now()}`,
        title: clean,
        section: addSection,
        area: area || null,
        priority: newPriority,
        done: false,
        completed_at: null
      }
      setDemoBoard(current => addBoardTask(current, task))
      setTitle('')
      setNewPriority(false)
      haptic('success')
      return
    }
    addMutation.mutate({
      title: clean,
      section: addSection,
      area: area || null,
      priority: newPriority,
      revision: board.revision
    })
  }

  const openTask = task => {
    setDraft({ ...task })
    setDeleteArmed(false)
  }

  const askHermes = async task => {
    const prompt = [
      'Help me with this personal task from my shared Tasks board:',
      `Task: ${task.title}`,
      `Status: ${task.section}`,
      task.area ? `Area: ${task.area}` : null,
      task.priority ? 'Priority: yes' : null,
      'First understand what I need, then help me take the next concrete action. Do not change the task unless I explicitly ask.'
    ].filter(Boolean).join('\n')
    setAsking(true)
    try {
      const sessionId = host.state.activeSessionId.get()
      if (sessionId) {
        await host.request('prompt.submit', { session_id: sessionId, text: prompt })
        host.navigate('/')
      } else {
        await navigator.clipboard.writeText(prompt)
        host.notify({ kind: 'info', title: 'Task context copied', message: 'Open a chat and paste it to ask Hermes.' })
        host.navigate('/')
      }
      setDraft(null)
    } catch (error) {
      host.notifyError(error, 'Could not ask Hermes')
    } finally {
      setAsking(false)
    }
  }

  const visible = useMemo(() => {
    if (!board) return emptySections()
    const query = search.trim().toLowerCase()
    const matches = task => {
      if (filter === 'priority' && !task.priority) return false
      if (filter !== 'all' && filter !== 'priority' && task.area !== filter) return false
      return !query || task.title.toLowerCase().includes(query) || (task.area || '').toLowerCase().includes(query)
    }
    return Object.fromEntries(ALL_SECTIONS.map(section => [section, (board.sections?.[section] || []).filter(matches)]))
  }, [board, filter, search])

  if (mode === 'live' && boardQuery.isLoading) {
    return jsx('div', { className: 'flex h-full items-center justify-center', children: jsx(GlyphSpinner, { className: 'size-5' }) })
  }

  if (mode === 'live' && boardQuery.isError) {
    return jsx('div', {
      className: 'flex h-full items-center justify-center p-6',
      children: jsx(ErrorState, {
        title: 'Tasks unavailable',
        description: boardQuery.error instanceof Error ? boardQuery.error.message : 'The task backend could not be reached.',
        children: jsxs('div', {
          className: 'flex gap-2',
          children: [
            jsx(Button, { size: 'sm', onClick: () => boardQuery.refetch(), children: 'Retry' }),
            jsx(Button, { size: 'sm', variant: 'secondary', onClick: () => setMode('demo'), children: 'Open demo' })
          ]
        })
      })
    })
  }

  if (!board) return null
  const focusId = board.focus_task_id || board.next_task_id
  const focusTask = ALL_SECTIONS.flatMap(section => board.sections?.[section] || []).find(task => task.id === focusId)

  return jsxs('div', {
    className: 'flex h-full min-h-0 flex-col overflow-hidden',
    children: [
      jsxs('header', {
        className: 'shrink-0 border-b border-(--ui-stroke-secondary) px-4 py-3 sm:px-5',
        children: [
          jsxs('div', {
            className: 'flex flex-wrap items-center justify-between gap-3',
            children: [
              jsxs('div', {
                className: 'min-w-0',
                children: [
                  jsxs('div', {
                    className: 'flex items-center gap-2',
                    children: [
                      jsx('h1', { className: 'text-base font-semibold text-foreground', children: 'Tasks' }),
                      mode === 'demo' ? jsx('span', { className: 'rounded bg-(--ui-accent)/10 px-1.5 py-0.5 text-[0.625rem] text-(--ui-accent)', children: 'isolated demo' }) : null
                    ]
                  }),
                  jsx('p', {
                    className: 'mt-0.5 truncate text-[0.6875rem] text-(--ui-text-quaternary)',
                    children: focusTask ? `${focusTask.section === 'Doing' ? 'Focus' : 'Up next'} · ${focusTask.title}` : 'One board. Two operators. Plain Markdown.'
                  })
                ]
              }),
              jsxs('div', {
                className: 'flex items-center gap-3',
                children: [
                  jsx(Count, { label: 'open', value: board.counts.open, strong: true }),
                  jsx(Count, { label: 'doing', value: board.wip.count }),
                  jsx(Count, { label: 'waiting', value: board.waiting_count }),
                  jsx(SegmentedControl, { onChange: setMode, options: VIEW_MODES, value: mode }),
                  mode === 'demo' ? jsx(Button, {
                    onClick: () => setDemoBoard(createDemoBoard()),
                    size: 'xs',
                    type: 'button',
                    variant: 'ghost',
                    children: 'Reset demo'
                  }) : jsx(Button, {
                    'aria-label': 'Refresh tasks',
                    disabled: boardQuery.isFetching,
                    onClick: () => boardQuery.refetch(),
                    size: 'icon-xs',
                    type: 'button',
                    variant: 'ghost',
                    children: boardQuery.isFetching ? jsx(GlyphSpinner, { className: 'size-3.5' }) : jsx(Codicon, { name: 'refresh', size: '0.875rem' })
                  })
                ]
              })
            ]
          }),
          jsxs('form', {
            className: 'mt-3 flex min-w-0 flex-wrap items-center gap-2',
            onSubmit: submit,
            children: [
              jsx(Input, {
                'aria-label': 'New task',
                className: 'min-w-48 flex-1',
                disabled: busy,
                onChange: event => setTitle(event.target.value),
                placeholder: `Add to ${addSection}…`,
                ref: addInputRef,
                value: title
              }),
              jsx(Input, {
                'aria-label': 'Area',
                className: 'w-28',
                disabled: busy,
                onChange: event => setNewArea(event.target.value),
                placeholder: 'Area',
                value: newArea
              }),
              jsx(Button, {
                'aria-label': 'Toggle priority',
                'aria-pressed': newPriority,
                onClick: () => setNewPriority(current => !current),
                size: 'icon-sm',
                type: 'button',
                variant: newPriority ? 'secondary' : 'ghost',
                children: jsx(Codicon, { name: 'flame', size: '0.875rem' })
              }),
              jsx(Button, {
                disabled: busy || !title.trim(),
                size: 'sm',
                type: 'submit',
                children: addMutation.isPending ? jsx(GlyphSpinner, { className: 'size-3.5' }) : 'Add'
              })
            ]
          }),
          jsxs('div', {
            className: 'mt-3 flex min-w-0 flex-wrap items-center justify-between gap-2',
            children: [
              jsx(AreaFilters, { areas: board.areas, onChange: setFilter, value: filter }),
              jsx(Button, {
                onClick: () => setAreaManagerOpen(true),
                size: 'xs',
                type: 'button',
                variant: 'ghost',
                children: 'Manage areas'
              }),
              jsx(SearchField, {
                'aria-label': 'Search tasks',
                containerClassName: 'ml-auto',
                inputRef: searchInputRef,
                onChange: setSearch,
                placeholder: 'Search tasks',
                value: search
              })
            ]
          })
        ]
      }),
      jsxs('main', {
        className: 'flex min-h-0 flex-1 gap-3 overflow-x-auto p-3 sm:p-4',
        children: [
          ...ALL_SECTIONS.map(section => jsx(BoardColumn, {
            section,
            tasks: visible[section],
            canonicalTasks: board.sections[section] || [],
            collapsed: collapsedSections.has(section),
            doingLimit: board.doing_limit,
            dragOver: dragOver === section,
            pendingId,
            onAddHere: nextSection => setAddSection(nextSection),
            onComplete: (task, done) => mutateTask(task.id, { section: done ? 'Done' : 'Next' }),
            onDropTask: (id, nextSection, placement = {}) => mutateTask(id, { section: nextSection, ...placement }),
            onOpen: openTask,
            onSetDragOver: setDragOver,
            onToggleCollapsed: toggleCollapsed
          }, section))
        ]
      }),
      jsx(AreaManager, {
        areas: board.areas,
        board,
        busy,
        onClose: () => setAreaManagerOpen(false),
        onCreate: name => mutateArea({ type: 'create', name }),
        onRemove: (area, replacement) => mutateArea({ type: 'remove', area, replacement }),
        onRename: (area, name) => mutateArea({ type: 'rename', area, name }),
        open: areaManagerOpen
      }),
      jsx(TaskEditor, {
        draft,
        deleteArmed,
        pending: pendingId === draft?.id,
        asking,
        onAsk: askHermes,
        onChange: setDraft,
        onClose: () => { setDraft(null); setDeleteArmed(false) },
        onDelete: () => deleteTask(draft.id),
        onSave: next => mutateTask(next.id, {
          title: next.title.trim(),
          section: next.section,
          area: normalizeAreaName(next.area),
          priority: Boolean(next.priority)
        })
      })
    ]
  })
}

function TasksStatus() {
  const boardQuery = useBoard(5000)
  if (!boardQuery.data) return null
  const { open } = boardQuery.data.counts
  const doing = boardQuery.data.wip?.count || 0
  return jsx('button', {
    className: cn(
      'inline-flex h-full items-center gap-1.5 px-1.5 text-[0.6875rem] tabular-nums transition-colors',
      'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
    ),
    onClick: () => {
      haptic('tap')
      host.navigate('/tasks')
    },
    title: 'Open Tasks',
    type: 'button',
    children: doing ? `${doing} doing · ${open} open` : `${open} tasks`
  })
}

export default {
  id: ID,
  name: 'Tasks',
  register(ctx) {
    pluginContext = ctx
    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/tasks' },
        render: () => jsx(TasksPage, {})
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: '/tasks', label: 'Tasks', codicon: 'checklist' }
      },
      {
        id: 'status',
        area: STATUSBAR_AREAS.right,
        order: 115,
        render: () => jsx(TasksStatus, {})
      }
    ])
  }
}
