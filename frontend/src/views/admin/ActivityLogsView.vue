<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { AlertCircle, CalendarRange, ChevronLeft, ChevronRight, Download, History, LoaderCircle } from 'lucide-vue-next'
import { getCounterCountLogs } from '../../services/counterAccounts'

const logs = ref([])
const loading = ref(true)
const error = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const rangeError = ref('')
const activeDateRange = ref(null)
const pageSize = ref(20)
const currentPage = ref(1)
const pageSizeOptions = [10, 20, 50, 100]
const totalPages = computed(() => Math.max(1, Math.ceil(logs.value.length / pageSize.value)))
const paginatedLogs = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return logs.value.slice(start, start + pageSize.value)
})
const firstVisibleRow = computed(() => (logs.value.length ? (currentPage.value - 1) * pageSize.value + 1 : 0))
const lastVisibleRow = computed(() => Math.min(currentPage.value * pageSize.value, logs.value.length))

// Reset pagination whenever the user changes the number of visible rows.
watch(pageSize, () => {
  currentPage.value = 1
})

// Format the quantity for display. Troubleshoot: numeric conversion and decimal rounding.
function quantity(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'
}

// Format the date and time using the browser locale. Troubleshoot: API timestamp and device timezone.
function timestamp(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

// Display empty metadata consistently in old/new comparisons.
function metadataValue(value) {
  return value === null || value === undefined || value === '' ? '(blank)' : value
}

// Summarize which product metadata fields changed in this audit event.
function changedFields(log) {
  const fields = []
  if (log.lotNoChanged) fields.push('Lot No.')
  if (log.productionDateChanged) fields.push('Production Date')
  if (log.expiryDateChanged) fields.push('Expiration Date')
  return fields.join(', ')
}

// Split a timestamp into local date and time for CSV export. Troubleshoot: invalid dates and the device timezone.
function dateAndTime(value) {
  if (!value) return { date: '', time: '' }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return { date: '', time: '' }
  // Pad each date/time component with a leading zero to produce two digits.
  const pad = (part) => String(part).padStart(2, '0')
  return {
    date: `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`,
    time: `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}:${pad(parsed.getSeconds())}`,
  }
}

// Escape CSV quotes and protect formula-like text. Troubleshoot: commas, quotes, and spreadsheet cell formatting.
function csvCell(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  let text = value === null || value === undefined ? '' : String(value)
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`
  return `"${text.replace(/"/g, '""')}"`
}

// Convert the CSV quantity to a number, or return a blank for invalid values. Troubleshoot: source values for numeric columns.
function csvNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : ''
}

// Generate and download the activity-log CSV. Troubleshoot: logs, column order, and csvCell/csvNumber formatting.
function exportCsv() {
  if (!logs.value.length) return

  const headers = [
    'Date',
    'Time',
    'Counter No.',
    'Counter Name',
    'Counter ID',
    'Cycle Count',
    'Detail ID',
    'Product',
    'Location',
    'Changed Fields',
    'Old Lot No.',
    'New Lot No.',
    'Old Production Date',
    'New Production Date',
    'Old Expiration Date',
    'New Expiration Date',
    'Old Count',
    'Actual C',
    'Actual PC',
    'Actual Total',
    'Variance',
  ]
  // Map each activity log to CSV column order, including local date/time and numeric quantities.
  const rows = logs.value.map((log) => {
    const counted = dateAndTime(log.countedAt)
    return [
      counted.date,
      counted.time,
      log.counterNumber,
      log.counterName,
      log.counterId,
      log.cycleCountCode || log.cycleCountId,
      log.detailId,
      log.description || `AI ID ${log.activeInventoryId || ''}`,
      log.location,
      changedFields(log),
      log.lotNoChanged ? metadataValue(log.lotNoFrom) : '',
      metadataValue(log.lotNo),
      log.productionDateChanged ? metadataValue(log.productionDateFrom) : '',
      metadataValue(log.productionDate),
      log.expiryDateChanged ? metadataValue(log.expiryDateFrom) : '',
      metadataValue(log.expiryDate),
      csvNumber(log.oldCount),
      csvNumber(log.actualCs),
      csvNumber(log.actualPc),
      csvNumber(log.actualTotal),
      csvNumber(log.variance),
    ]
  })
  // Escape each CSV cell and join the row with commas.
  const csv = [headers, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n')
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  const rangeLabel = activeDateRange.value
    ? `${activeDateRange.value.dateFrom}-to-${activeDateRange.value.dateTo}`
    : dateAndTime(new Date()).date
  link.download = `counter-activity-logs-${rangeLabel}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

// Load activity logs and manage loading/error state. Troubleshoot: getCounterCountLogs response.
async function loadLogs(filters = {}) {
  loading.value = true
  error.value = ''
  try {
    logs.value = await getCounterCountLogs(filters)
    currentPage.value = 1
    activeDateRange.value = filters.dateFrom && filters.dateTo ? { ...filters } : null
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    loading.value = false
  }
}

// Validate and generate the inclusive From/To activity report.
function generateDateRange() {
  rangeError.value = ''
  if (!dateFrom.value || !dateTo.value) {
    rangeError.value = 'Select both From and To dates.'
    return
  }
  if (dateFrom.value > dateTo.value) {
    rangeError.value = 'From date cannot be later than To date.'
    return
  }
  loadLogs({ dateFrom: dateFrom.value, dateTo: dateTo.value })
}

// Clear the report period and restore all available activity logs.
function resetDateRange() {
  dateFrom.value = ''
  dateTo.value = ''
  rangeError.value = ''
  loadLogs()
}

onMounted(loadLogs)
</script>

<template>
  <main class="page log-page">
    <div class="page-header">
      <div class="page-title-group"><div class="page-title-icon"><History :size="22" /></div><div><h1 class="page-title">Counter Activity Logs</h1><p class="page-subtitle">Who counted each product and the quantities they saved.</p></div></div>
      <div class="header-actions">
        
        <button class="export-button" type="button" :disabled="loading || !logs.length" @click="exportCsv"><Download :size="17" />Export CSV</button>
      </div>
    </div>

    <form class="date-range-card card" :aria-busy="loading" @submit.prevent="generateDateRange">
      <div class="date-range-title"><CalendarRange :size="20" /><div><strong>Generate by date range</strong><small>Includes activity from both selected dates.</small></div></div>
      <label><span>From</span><input v-model="dateFrom" type="date" :max="dateTo || undefined" required /></label>
      <label><span>To</span><input v-model="dateTo" type="date" :min="dateFrom || undefined" required /></label>
      <div class="date-range-actions"><button class="generate-button" type="submit" :disabled="loading">{{ loading ? 'Generating...' : 'Generate Report' }}</button><button class="reset-button" type="button" :disabled="loading || (!dateFrom && !dateTo && !activeDateRange)" @click="resetDateRange">Reset</button></div>
      <p v-if="rangeError" class="range-error" role="alert">{{ rangeError }}</p>
    </form>

    <section v-if="loading" class="card state-card"><LoaderCircle class="spin" :size="27" />Loading count activity...</section>
    <section v-else-if="error" class="card state-card error-state"><AlertCircle :size="27" /><strong>Could not load activity</strong><span>{{ error }}</span><button class="btn btn-secondary" type="button" @click="loadLogs">Try again</button></section>
    <section v-else class="card logs-card">
      <div class="log-summary">
        <div class="log-summary-copy"><strong>{{ logs.length }} {{ logs.length === 1 ? 'count event' : 'count events' }}</strong><span>{{ activeDateRange ? `${activeDateRange.dateFrom} to ${activeDateRange.dateTo}` : 'All dates · newest activity first' }}</span></div>
        <label v-if="logs.length" class="page-size"><span>Rows per page</span><select v-model.number="pageSize" aria-label="Rows per page"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option></select></label>
      </div>
      <div v-if="logs.length" class="table-scroll" tabindex="0" aria-label="Counter activity results; scroll horizontally for more columns">
        <table v-if="activeDateRange" class="raw-report-table">
          <thead><tr><th>Date</th><th>Time</th><th>Counter No.</th><th>Counter Name</th><th>Counter ID</th><th>Cycle Count</th><th>Detail ID</th><th>Product</th><th>Location</th><th>Changed Fields</th><th>Old Lot No.</th><th>New Lot No.</th><th>Old Production Date</th><th>New Production Date</th><th>Old Expiration Date</th><th>New Expiration Date</th><th>Old Count</th><th>Actual CASE</th><th>Actual PC</th><th>Actual Total</th><th>Variance</th></tr></thead>
          <tbody><tr v-for="log in paginatedLogs" :key="log.id"><td>{{ dateAndTime(log.countedAt).date }}</td><td>{{ dateAndTime(log.countedAt).time }}</td><td>{{ log.counterNumber }}</td><td>{{ log.counterName }}</td><td>{{ log.counterId }}</td><td>{{ log.cycleCountCode || log.cycleCountId }}</td><td>{{ log.detailId }}</td><td>{{ log.description || `AI ID ${log.activeInventoryId || '—'}` }}</td><td>{{ log.location || '—' }}</td><td>{{ changedFields(log) || '—' }}</td><td>{{ log.lotNoChanged ? metadataValue(log.lotNoFrom) : '—' }}</td><td>{{ metadataValue(log.lotNo) }}</td><td>{{ log.productionDateChanged ? metadataValue(log.productionDateFrom) : '—' }}</td><td>{{ metadataValue(log.productionDate) }}</td><td>{{ log.expiryDateChanged ? metadataValue(log.expiryDateFrom) : '—' }}</td><td>{{ metadataValue(log.expiryDate) }}</td><td>{{ quantity(log.oldCount) }}</td><td>{{ quantity(log.actualCs) }}</td><td>{{ quantity(log.actualPc) }}</td><td>{{ quantity(log.actualTotal) }}</td><td :class="{ variance: Number(log.variance) !== 0 }">{{ quantity(log.variance) }}</td></tr></tbody>
        </table>
        <table v-else class="preview-table">
          <thead><tr><th>Date/Time</th><th>Counter</th><th>Cycle Count</th><th>Product</th><th>Changed Fields</th><th>Actual Total</th><th>Variance</th></tr></thead>
          <tbody><tr v-for="log in paginatedLogs" :key="log.id"><td>{{ timestamp(log.countedAt) }}</td><td><strong>{{ log.counterName }}</strong><small>Counter {{ log.counterNumber }}</small></td><td>{{ log.cycleCountCode || log.cycleCountId }}</td><td>{{ log.description || `AI ID ${log.activeInventoryId || '—'}` }}</td><td>{{ changedFields(log) || 'None' }}</td><td>{{ quantity(log.actualTotal) }}</td><td :class="{ variance: Number(log.variance) !== 0 }">{{ quantity(log.variance) }}</td></tr></tbody>
        </table>
      </div>
      <div v-if="logs.length" class="table-pagination">
        <span class="page-range">{{ firstVisibleRow }}–{{ lastVisibleRow }} of {{ logs.length }}</span>
        <div class="page-buttons">
          <button type="button" aria-label="Previous page" :disabled="currentPage === 1" @click="currentPage--"><ChevronLeft :size="18" /></button>
          <span>Page {{ currentPage }} of {{ totalPages }}</span>
          <button type="button" aria-label="Next page" :disabled="currentPage === totalPages" @click="currentPage++"><ChevronRight :size="18" /></button>
        </div>
      </div>
      <p v-else class="empty-state">No product counts have been saved by a Counter yet.</p>
    </section>
  </main>
</template>

<style scoped>
.log-page{max-width:1500px;margin:0 auto}.header-actions{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:8px}.export-button{min-height:42px;padding:9px 13px;border:1px solid #15803d;border-radius:10px;background:#15803d;color:#fff;display:inline-flex;align-items:center;justify-content:center;gap:7px;font-size:13px;font-weight:900;cursor:pointer}.export-button:hover:not(:disabled){background:#166534}.export-button:disabled{opacity:.5;cursor:not-allowed}.state-card{min-height:260px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;padding:24px;text-align:center;color:#64748b}.error-state svg{color:#b91c1c}.logs-card{overflow:hidden}.log-summary{display:flex;align-items:center;justify-content:space-between;padding:15px 18px;border-bottom:1px solid #e5ebe6;color:#334155}.log-summary span{font-size:12px;color:#64748b}.table-scroll{max-width:100%;overflow-x:auto}.table-scroll:focus-visible{outline-offset:-3px}table{width:100%;border-collapse:collapse}.raw-report-table{min-width:2350px}.preview-table{min-width:900px}th,td{text-align:left;padding:10px 9px;border-bottom:1px solid #edf1ed;font-size:12px;white-space:nowrap}th{position:sticky;top:0;background:#f8faf8;color:#475569;font-size:10px;text-transform:uppercase}td strong,td small{display:block}td small{margin-top:3px;color:#64748b;font-size:10px}.variance{color:#b91c1c;font-weight:900}.empty-state{padding:50px 20px;text-align:center;color:#64748b}
.date-range-card{display:grid;grid-template-columns:minmax(220px,1fr) repeat(2,minmax(150px,210px)) auto;align-items:end;gap:12px;margin-bottom:16px;padding:16px}.date-range-title{display:flex;align-items:center;gap:9px;color:#166534}.date-range-title div,.date-range-card label span{display:block}.date-range-title small{display:block;margin-top:2px;color:#64748b;font-size:11px}.date-range-card label span{margin-bottom:5px;color:#475569;font-size:11px;font-weight:900;text-transform:uppercase}.date-range-card input{width:100%;min-height:42px;padding:6px 9px;border:1px solid #cfd9d1;border-radius:8px;background:#fff;color:#1e293b;font-weight:700}.date-range-card input:focus{border-color:#15803d;outline:3px solid rgba(21,128,61,.12)}.date-range-actions{display:flex;gap:7px}.generate-button,.reset-button{min-height:42px;padding:0 14px;border-radius:8px;font-weight:900}.generate-button{border:1px solid #166534;background:#166534;color:#fff}.reset-button{border:1px solid #cbd5e1;background:#fff;color:#475569}.generate-button:disabled,.reset-button:disabled{opacity:.5}.range-error{grid-column:1/-1;margin:0;color:#b91c1c;font-size:12px;font-weight:800}
.table-pagination{display:flex;align-items:center;justify-content:flex-end;gap:20px;min-height:52px;padding:7px 12px;border-top:1px solid #e5ebe6;background:#fff;color:#475569;font-size:12px;font-weight:700}.page-size{display:flex;align-items:center;gap:8px}.page-size select{min-width:68px;height:36px;padding:0 9px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#1e293b;font-weight:800}.page-size select:focus{border-color:#15803d;outline:3px solid rgba(21,128,61,.12)}.page-range{white-space:nowrap}.page-buttons{display:flex;align-items:center;gap:7px}.page-buttons button{width:36px;height:36px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#166534;display:grid;place-items:center;cursor:pointer}.page-buttons button:hover:not(:disabled){background:#f0fdf4;border-color:#15803d}.page-buttons button:disabled{color:#94a3b8;background:#f8fafc;cursor:not-allowed}
.log-summary{gap:16px;padding-top:10px;padding-bottom:10px}.log-summary-copy{display:flex;flex-direction:column;gap:3px}.log-summary-copy span{font-size:12px;color:#64748b}.log-summary>.page-size{flex-shrink:0}.log-summary>.page-size span{font-size:11px;font-weight:800;color:#475569}
@media(max-width:800px){.date-range-card{grid-template-columns:1fr 1fr}.date-range-title,.date-range-actions,.range-error{grid-column:1/-1}.date-range-actions button{flex:1}}
@media(max-width:600px){.log-page{padding:14px}.header-actions{width:100%;justify-content:stretch}.export-button{width:100%}.date-range-card{grid-template-columns:1fr}.date-range-card label,.date-range-title,.date-range-actions,.range-error{grid-column:1}.date-range-actions button{min-height:44px}.log-summary{align-items:flex-start;gap:5px;flex-direction:column}.table-pagination{justify-content:space-between;gap:9px;flex-wrap:wrap}.page-size span,.page-buttons span{display:none}.page-buttons{margin-left:auto}}
@media(max-width:600px){.log-summary{align-items:center;flex-direction:row;gap:10px}.log-summary>.page-size span{display:inline}.table-pagination .page-buttons span{display:none}}
</style>
