<template>
  <div class="k-data-table" :class="{ 'k-data-table--dense': dense }">
    <div class="k-data-table__scroller">
      <table>
        <caption v-if="caption">{{ caption }}</caption>
        <thead :class="{ 'is-sticky': stickyHeader }">
          <tr>
            <th
              v-for="column in columns"
              :key="column.key"
              scope="col"
              :class="[column.headerClass, `is-${column.align || 'left'}`]"
              :style="column.width ? { width: column.width } : undefined"
            >
              <slot :name="`header-${column.key}`" :column="column">
                {{ column.label }}
              </slot>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td class="k-data-table__state" :colspan="Math.max(columns.length, 1)">
              <slot name="loading">正在加载…</slot>
            </td>
          </tr>
          <tr v-else-if="!items.length">
            <td class="k-data-table__state" :colspan="Math.max(columns.length, 1)">
              <slot name="empty">{{ emptyText }}</slot>
            </td>
          </tr>
          <template v-else>
            <tr
              v-for="(item, rowIndex) in items"
              :key="resolveRowKey(item, rowIndex)"
              :class="{ 'is-clickable': rowClickable }"
              :tabindex="rowClickable ? 0 : undefined"
              @click="rowClickable && emit('rowClick', item, rowIndex)"
              @keydown.enter="rowClickable && emit('rowClick', item, rowIndex)"
            >
              <td
                v-for="column in columns"
                :key="column.key"
                :class="[column.cellClass, `is-${column.align || 'left'}`]"
              >
                <slot
                  :name="`cell-${column.key}`"
                  :item="item"
                  :value="resolveValue(item, column, rowIndex)"
                  :column="column"
                  :row-index="rowIndex"
                >
                  {{ formatValue(item, column, rowIndex) }}
                </slot>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  columns: {
    type: Array,
    default: () => []
  },
  items: {
    type: Array,
    default: () => []
  },
  rowKey: {
    type: [String, Function],
    default: 'id'
  },
  caption: {
    type: String,
    default: ''
  },
  emptyText: {
    type: String,
    default: '暂无数据'
  },
  dense: Boolean,
  loading: Boolean,
  stickyHeader: Boolean,
  rowClickable: Boolean
})

const emit = defineEmits(['rowClick'])

const getByPath = (item, path) => String(path)
  .split('.')
  .reduce((value, key) => value?.[key], item)

const resolveValue = (item, column, rowIndex) => {
  if (typeof column.value === 'function') return column.value(item, rowIndex)
  return getByPath(item, column.key)
}

const formatValue = (item, column, rowIndex) => {
  const value = resolveValue(item, column, rowIndex)
  if (typeof column.format === 'function') return column.format(value, item, rowIndex)
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

const resolveRowKey = (item, rowIndex) => {
  if (typeof props.rowKey === 'function') return props.rowKey(item, rowIndex)
  return getByPath(item, props.rowKey) ?? rowIndex
}
</script>

<style scoped>
.k-data-table {
  width: 100%;
  min-width: 0;
  overflow: hidden;
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border);
  border-radius: var(--k-radius-md);
}

.k-data-table__scroller {
  width: 100%;
  overflow: auto;
}

table {
  width: 100%;
  border-spacing: 0;
  border-collapse: separate;
  color: var(--k-color-text);
  font-family: var(--k-font-sans);
  font-size: var(--k-text-ui);
  font-variant-numeric: tabular-nums;
}

caption {
  padding: var(--k-space-3) var(--k-space-4);
  color: var(--k-color-text-secondary);
  font-size: var(--k-text-body);
  font-weight: 600;
  text-align: left;
}

th,
td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--k-color-border);
  line-height: 1.4;
  text-align: left;
  vertical-align: middle;
}

th {
  color: var(--k-color-text-secondary);
  background: var(--k-color-surface-subtle);
  font-size: var(--k-text-meta);
  font-weight: 650;
  letter-spacing: 0.01em;
  white-space: nowrap;
}

thead.is-sticky th {
  position: sticky;
  top: 0;
  z-index: 1;
}

tbody tr:last-child td {
  border-bottom: 0;
}

tbody tr:not(.is-clickable):hover td {
  background: rgba(31, 93, 69, 0.018);
}

tbody tr.is-clickable {
  cursor: pointer;
}

tbody tr.is-clickable:hover td,
tbody tr.is-clickable:focus-visible td {
  background: var(--k-color-brand-050);
}

tbody tr.is-clickable:focus-visible {
  outline: 2px solid var(--k-color-brand-500);
  outline-offset: -2px;
}

.is-center {
  text-align: center;
}

.is-right {
  text-align: right;
}

.k-data-table--dense th,
.k-data-table--dense td {
  padding: 0.5rem 0.75rem;
}

.k-data-table__state {
  height: 7rem;
  color: var(--k-color-text-muted);
  text-align: center;
}
</style>
