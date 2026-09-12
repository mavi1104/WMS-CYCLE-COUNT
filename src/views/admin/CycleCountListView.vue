<script setup>
import { computed, onMounted, ref } from 'vue'
import { AlertCircle, CalendarDays, CalendarRange, CircleDot, ClipboardList, ListChecks, LoaderCircle, RotateCcw, Search, Warehouse } from 'lucide-vue-next'
import { getCycleCounts } from '../../services/cycleCounts'

const cycleCounts = ref([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const warehouse = ref('')
const status = ref('')
const fromDate = ref('')
const toDate = ref('')

// Collect unique non-null warehouse IDs and sort them numerically for the filter.
const warehouses = computed(() => [...new Set(cycleCounts.value.map((row) => row.warehouseId).filter((value) => value !== null))].sort((a, b) => Number(a) - Number(b)))
// Collect unique non-null status IDs and sort them numerically for the filter.
const statuses = computed(() => [...new Set(cycleCounts.value.map((row) => row.statusId).filter((value) => value !== null))].sort((a, b) => Number(a) - Number(b)))
// Filter the list using search and the current filters. Troubleshoot: source rows and filter values.
const rows = computed(() => cycleCounts.value.filter((row) => {
  const q = search.value.trim().toLowerCase()
  const searchable = `${row.code || ''} ${row.remarks || ''}`.toLowerCase()
  return (!q || searchable.includes(q))
    && (!warehouse.value || String(row.warehouseId) === warehouse.value)
    && (!status.value || String(row.statusId) === status.value)
    && (!fromDate.value || row.transDate >= fromDate.value)
    && (!toDate.value || row.transDate <= toDate.value)
}))

// Load cycle counts and manage loading/error state. Troubleshoot: getCycleCounts filters and API response.
async function loadCycleCounts() {
  loading.value = true
  error.value = ''
  try {
    cycleCounts.value = await getCycleCounts('admin-cycle-counts')
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    loading.value = false
  }
}

// Clear search, warehouse, status, and date filters. Troubleshoot: filter values when rows are missing.
function reset() {
  search.value = ''
  warehouse.value = ''
  status.value = ''
  fromDate.value = ''
  toDate.value = ''
}

onMounted(loadCycleCounts)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div class="page-title-group"><div class="page-title-icon"><ClipboardList :size="22" /></div><div><h1 class="page-title">WMS Cycle Counts</h1><p class="page-subtitle">Review open daily Cycle Count records.</p></div></div>
    </div>

    <form class="card filters" aria-label="Filter Cycle Counts" @submit.prevent>
      <div><span class="label label-with-icon"><Search :size="14" />Search</span><div class="search-box"><Search :size="17" /><input v-model="search" class="input" placeholder="Cycle Count No. or remarks" /></div></div>
      <div><span class="label label-with-icon"><Warehouse :size="14" />Warehouse ID</span><select v-model="warehouse" class="select"><option value="">All warehouses</option><option v-for="id in warehouses" :key="id" :value="String(id)">{{ id }}</option></select></div>
      <div><span class="label label-with-icon"><CircleDot :size="14" />Status ID</span><select v-model="status" class="select"><option value="">All statuses</option><option v-for="id in statuses" :key="id" :value="String(id)">{{ id }}</option></select></div>
      <div><span class="label label-with-icon"><CalendarDays :size="14" />From</span><input v-model="fromDate" type="date" class="input" :max="toDate || undefined" /></div>
      <div><span class="label label-with-icon"><CalendarRange :size="14" />To</span><input v-model="toDate" type="date" class="input" :min="fromDate || undefined" /></div>
      <button class="btn btn-secondary reset" type="button" @click="reset"><RotateCcw :size="16" />Reset</button>
    </form>

    <section v-if="loading" class="card state-card"><LoaderCircle class="spin" :size="27" /><strong>Loading cycle counts…</strong></section>
    <section v-else-if="error" class="card state-card error-state"><AlertCircle :size="27" /><strong>Could not load database records</strong><span>{{ error }}</span><button class="btn btn-secondary" type="button" @click="loadCycleCounts">Try again</button></section>
    <section v-else class="table-card card">
      <div class="table-head"><ListChecks :size="21" /><div><strong>Cycle Count Records</strong><span aria-live="polite">{{ rows.length }} {{ rows.length === 1 ? 'record' : 'records' }}</span></div></div>
      <div v-if="rows.length" class="table-wrap no-border" tabindex="0" aria-label="Cycle Count records; scroll horizontally for more columns"><table><thead><tr><th>Cycle Count No.</th><th>Date</th><th>Warehouse ID</th><th>Status ID</th><th>Type</th><th>Remarks</th></tr></thead><tbody><tr v-for="row in rows" :key="row.id"><td><strong>{{ row.code || row.id }}</strong><small class="record-id">DB ID: {{ row.id }}</small></td><td>{{ row.transDate || '—' }}</td><td>{{ row.warehouseId ?? '—' }}</td><td><span class="badge badge-slate">{{ row.statusId ?? '—' }}</span></td><td>{{ row.ccType || '—' }}</td><td>{{ row.remarks || '—' }}</td></tr></tbody></table></div>
      <div v-else class="empty-state">No matching database records.</div>
    </section>
  </main>
</template>

<style scoped>
.filters{padding:16px;display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr auto;gap:12px;align-items:end;margin-bottom:18px}.search-box{position:relative}.search-box svg{position:absolute;left:12px;top:50%;transform:translateY(-50%);color:#64748b}.search-box .input{padding-left:38px}.reset{height:42px}.table-card{overflow:hidden}.table-head{display:flex;align-items:center;gap:10px;padding:16px 18px;border-bottom:1px solid #e5ebe6;color:#166534}.table-head strong,.table-head span{display:block}.table-head span{font-size:12px;color:#64748b;margin-top:3px}.no-border{border:0;border-radius:0}.no-border:focus-visible{outline-offset:-3px}.record-id{display:block;margin-top:3px;color:#64748b;font-weight:600}.state-card,.empty-state{min-height:180px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;padding:24px;text-align:center;color:#64748b}.state-card strong{color:#334155}.error-state svg{color:#b91c1c}
@media(max-width:1100px){.filters{grid-template-columns:repeat(2,minmax(0,1fr))}.reset{width:100%}}@media(max-width:620px){.filters{grid-template-columns:1fr}}
</style>
