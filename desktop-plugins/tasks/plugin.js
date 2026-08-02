import {
  Button,
  Checkbox,
  Codicon,
  EmptyState,
  ErrorState,
  GlyphSpinner,
  Input,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  SegmentedControl,
  cn,
  haptic,
  host,
  useMutation,
  useQuery,
  useQueryClient
} from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'tasks'
const QUERY_KEY = [ID, 'board']
const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'priority', label: 'Priority' },
  { id: 'work', label: 'Work' },
  { id: 'life', label: 'Life' }
]
const SECTION_ORDER = ['Now', 'Waiting', 'Later', 'Done']
let pluginContext = null

function request(path, options) {
  if (!pluginContext) return Promise.reject(new Error('Tasks plugin is not ready'))
  return pluginContext.rest(path, options)
}

function useBoard(refetchInterval = 2500) {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => request('/board'),
    refetchInterval,
    staleTime: 800,
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

function TaskRow({ task, completingId, onComplete }) {
  const completing = completingId === task.id
  return jsxs('div', {
    className: cn(
      'group flex min-h-10 items-start gap-3 rounded-md border border-transparent px-2.5 py-2 transition-colors',
      'hover:border-(--ui-stroke-secondary) hover:bg-(--ui-bg-secondary)',
      completing && 'opacity-60'
    ),
    children: [
      jsx(Checkbox, {
        'aria-label': task.done ? `Reopen ${task.title}` : `Complete ${task.title}`,
        checked: task.done,
        className: 'mt-0.5',
        disabled: completing,
        onCheckedChange: checked => onComplete(task.id, checked === true)
      }),
      jsxs('div', {
        className: 'min-w-0 flex-1',
        children: [
          jsx('div', {
            className: cn(
              'break-words text-[0.8125rem] leading-5 text-foreground',
              task.done && 'text-(--ui-text-quaternary) line-through'
            ),
            children: task.title
          }),
          jsxs('div', {
            className: 'mt-0.5 flex items-center gap-2 text-[0.625rem] uppercase tracking-wide text-(--ui-text-quaternary)',
            children: [
              task.priority
                ? jsxs('span', {
                    className: 'inline-flex items-center gap-1 font-medium text-(--ui-accent)',
                    children: [jsx(Codicon, { name: 'flame', size: '0.6875rem' }), 'priority']
                  })
                : null,
              task.area ? jsx('span', { children: task.area }) : null
            ]
          })
        ]
      }),
      completing ? jsx(GlyphSpinner, { className: 'mt-1 size-3.5' }) : null
    ]
  })
}

function Section({ name, tasks, completingId, onComplete }) {
  if (!tasks.length) return null
  return jsxs('section', {
    className: 'space-y-1',
    children: [
      jsxs('div', {
        className: 'flex items-center gap-2 px-2.5 pb-1 pt-3',
        children: [
          jsx('h2', { className: 'text-xs font-semibold text-foreground', children: name }),
          jsx('span', {
            className: 'text-[0.625rem] tabular-nums text-(--ui-text-quaternary)',
            children: tasks.length
          })
        ]
      }),
      ...tasks.map(task =>
        jsx(TaskRow, { task, completingId, onComplete }, task.id)
      )
    ]
  })
}

function TasksPage() {
  const queryClient = useQueryClient()
  const boardQuery = useBoard()
  const [title, setTitle] = useState('')
  const [filter, setFilter] = useState('all')
  const [hideDone, setHideDone] = useState(false)
  const [completingId, setCompletingId] = useState(null)

  const addMutation = useMutation({
    mutationFn: nextTitle => request('/tasks', { method: 'POST', body: { title: nextTitle, section: 'Now' } }),
    onSuccess: board => {
      queryClient.setQueryData(QUERY_KEY, board)
      setTitle('')
      haptic('success')
    },
    onError: error => host.notifyError(error, 'Could not add task')
  })

  const completeMutation = useMutation({
    mutationFn: ({ id, done }) => request(`/tasks/${encodeURIComponent(id)}/complete`, { method: 'PATCH', body: { done } }),
    onMutate: ({ id }) => setCompletingId(id),
    onSuccess: board => {
      queryClient.setQueryData(QUERY_KEY, board)
      haptic('success')
    },
    onError: error => {
      host.notifyError(error, 'Task changed elsewhere — refreshing')
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onSettled: () => setCompletingId(null)
  })

  const submit = event => {
    event.preventDefault()
    const clean = title.trim()
    if (clean && !addMutation.isPending) addMutation.mutate(clean)
  }

  if (boardQuery.isLoading) {
    return jsx('div', {
      className: 'flex h-full items-center justify-center',
      children: jsx(GlyphSpinner, { className: 'size-5' })
    })
  }

  if (boardQuery.isError) {
    return jsx('div', {
      className: 'flex h-full items-center justify-center p-6',
      children: jsx(ErrorState, {
        title: 'Tasks unavailable',
        description: boardQuery.error instanceof Error ? boardQuery.error.message : 'The task backend could not be reached.',
        children: jsx(Button, { size: 'sm', onClick: () => boardQuery.refetch(), children: 'Retry' })
      })
    })
  }

  const board = boardQuery.data
  const matches = task => {
    if (hideDone && task.done) return false
    if (filter === 'all') return true
    if (filter === 'priority') return task.priority && !task.done
    return task.area === filter
  }
  const visible = Object.fromEntries(
    SECTION_ORDER.map(section => [section, (board.sections[section] || []).filter(matches)])
  )
  const visibleCount = Object.values(visible).reduce((total, tasks) => total + tasks.length, 0)

  const handleComplete = (id, done) => {
    completeMutation.mutate({ id, done })
  }

  return jsxs('div', {
    className: 'flex h-full min-h-0 flex-col',
    children: [
      jsxs('header', {
        className: 'shrink-0 border-b border-(--ui-stroke-secondary) px-5 py-4',
        children: [
          jsxs('div', {
            className: 'flex flex-wrap items-center justify-between gap-3',
            children: [
              jsxs('div', {
                children: [
                  jsx('h1', { className: 'text-base font-semibold text-foreground', children: 'Tasks' }),
                  jsx('p', {
                    className: 'mt-0.5 text-[0.6875rem] text-(--ui-text-quaternary)',
                    children: 'Shared directly with Hermes · tasks.md'
                  })
                ]
              }),
              jsxs('div', {
                className: 'flex items-center gap-4',
                children: [
                  jsx(Count, { label: 'open', value: board.counts.open, strong: true }),
                  jsx(Count, { label: 'priority', value: board.counts.priority }),
                  jsx(Count, { label: 'done', value: board.counts.done }),
                  jsx(Button, {
                    'aria-label': 'Refresh tasks',
                    disabled: boardQuery.isFetching,
                    onClick: () => boardQuery.refetch(),
                    size: 'icon-xs',
                    variant: 'ghost',
                    children: boardQuery.isFetching
                      ? jsx(GlyphSpinner, { className: 'size-3.5' })
                      : jsx(Codicon, { name: 'refresh', size: '0.875rem' })
                  })
                ]
              })
            ]
          }),
          jsxs('form', {
            className: 'mt-4 flex gap-2',
            onSubmit: submit,
            children: [
              jsx(Input, {
                'aria-label': 'New task',
                className: 'min-w-0 flex-1',
                disabled: addMutation.isPending,
                onChange: event => setTitle(event.target.value),
                placeholder: 'Add a concrete next action…',
                value: title
              }),
              jsx(Button, {
                disabled: !title.trim() || addMutation.isPending,
                size: 'sm',
                type: 'submit',
                children: addMutation.isPending ? jsx(GlyphSpinner, { className: 'size-3.5' }) : 'Add'
              })
            ]
          }),
          jsxs('div', {
            className: 'mt-3 flex flex-wrap items-center gap-2',
            children: [
              jsx(SegmentedControl, {
                onChange: setFilter,
                options: FILTERS,
                value: filter
              }),
              jsx(Button, {
                'aria-label': 'Hide completed tasks',
                'aria-pressed': hideDone,
                onClick: () => setHideDone(current => !current),
                size: 'xs',
                type: 'button',
                variant: 'ghost',
                children: hideDone ? 'Done hidden' : 'Hide done'
              })
            ]
          })
        ]
      }),
      jsx('main', {
        className: 'min-h-0 flex-1 overflow-y-auto px-3 pb-8 sm:px-5',
        children: visibleCount
          ? SECTION_ORDER.map(section =>
              jsx(Section, {
                name: section,
                tasks: visible[section],
                completingId,
                onComplete: handleComplete
              }, section)
            )
          : jsx(EmptyState, {
              className: 'mt-16',
              title: filter === 'all' ? 'No tasks' : `No ${filter} tasks`,
              description: filter === 'all' ? 'Add the next concrete action above.' : 'Try another filter.'
            })
      })
    ]
  })
}

function TasksStatus() {
  const boardQuery = useBoard(5000)
  if (!boardQuery.data) return null
  const { open, priority } = boardQuery.data.counts
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
    children: priority ? `${open} tasks · ${priority} priority` : `${open} tasks`
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
