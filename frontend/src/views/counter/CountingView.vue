<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertCircle, Boxes, CalendarClock, CalendarDays, Check, ChevronDown, ChevronLeft, ChevronRight, CircleCheckBig, Info, MapPin, Package, PackageOpen, PackageSearch, Save, Search, ShoppingBag, Tag } from 'lucide-vue-next'
import { consumeCountingHandoff, getCycleCountDetails, updateActualCount } from '../../services/cycleCounts'
import { releaseCounterSession } from '../../services/counterSession.js'


const route = useRoute()
const router = useRouter()
const counterConnection = inject('counterConnection', null)
const counterSession = ref(null)
const rows = ref([])
const query = ref('')
const searchOpen = ref(false)
const productStatusFilter = ref('all')
const loading = ref(true)
const error = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const mobileRowIndex = ref(0)
const mobileListOpen = ref(true)
const completionMessageOpen = ref(false)
const completedOnOpen = ref(false)
const completionPromptShown = ref(false)
const finishingCycleCount = ref(false)
const findCard = ref(null)
const productStart = ref(null)
const activeDetailId = ref(null)
const minimumLoadingTime = 1000
const connectionBlocked = computed(() => Boolean(
  counterConnection?.connectionLost?.value || counterConnection?.lockExpired?.value,
))

// Filter the warehouse picker by product name so Counters can find what is physically in front of them.
const matchingProducts = computed(() => {
  const search = query.value.trim().toLowerCase()
  if (!search) return rows.value
  return rows.value.filter((row) => String(row.description ?? '').toLowerCase().includes(search))
})

const countedProductCount = computed(() => matchingProducts.value.filter((row) => row._saved).length)
const uncountedProductCount = computed(() => matchingProducts.value.length - countedProductCount.value)
const filtered = computed(() => {
  if (productStatusFilter.value === 'counted') return matchingProducts.value.filter((row) => row._saved)
  if (productStatusFilter.value === 'uncounted') return matchingProducts.value.filter((row) => !row._saved)
  return matchingProducts.value
})

function toggleProductStatusFilter(filter) {
  productStatusFilter.value = productStatusFilter.value === filter ? 'all' : filter
  currentPage.value = 1
  mobileRowIndex.value = 0
}

// Calculate the number of pages from filtered rows and pageSize.
const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
// Calculate the first row number on the current desktop page.
const pageStart = computed(() => filtered.value.length ? ((currentPage.value - 1) * pageSize.value) + 1 : 0)
// Limit the last row number to the length of the filtered list.
const pageEnd = computed(() => Math.min(currentPage.value * pageSize.value, filtered.value.length))
// Select rows for the current desktop page. Troubleshoot: pageStart/pageEnd.
const paginated = computed(() => filtered.value.slice(pageStart.value - 1, pageEnd.value))
// Select one mobile product using mobileRowIndex.
const mobilePaginated = computed(() => filtered.value.slice(mobileRowIndex.value, mobileRowIndex.value + 1))

// Match the responsive card layout: phones and touch tablets use the product picker;
// laptop-sized screens with a mouse or trackpad open the desktop raw table directly.
function usesMobileProductFlow() {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  const compactWidth = window.matchMedia('(max-width: 1366px)').matches
  const phoneWidth = window.matchMedia('(max-width: 767px)').matches
  const touchCapable = (
    (typeof navigator !== 'undefined' && Number(navigator.maxTouchPoints) > 0)
    || 'ontouchstart' in window
  )
  return phoneWidth || (compactWidth && touchCapable)
}

// Select a packing icon from the InventoryMaster packaging label.
function packingIcon(packaging) {
  const label = String(packaging ?? '').trim().toLowerCase()
  if (/bag|sack|pouch/.test(label)) return ShoppingBag
  if (/box|carton|case/.test(label)) return Package
  return PackageOpen
}

// Open the existing count card for the product selected from the compact warehouse list.
function selectMobileProduct(index) {
  const selectedProduct = filtered.value[index]
  productStatusFilter.value = 'all'
  mobileRowIndex.value = Math.max(0, matchingProducts.value.findIndex((row) => row.detailId === selectedProduct?.detailId))
  mobileListOpen.value = false
  activeDetailId.value = null
  scrollToProducts()
}

// Return to the searchable product list without discarding any saved data.
function showProductList() {
  activeDetailId.value = null
  mobileListOpen.value = true
  window.scrollTo({ top: 0, behavior: 'auto' })
}

// Open the completed product list for review without implying another count is required.
function reviewCompletedCounts() {
  completionMessageOpen.value = false
  completedOnOpen.value = false
  mobileListOpen.value = true
}

// Use the completion dialog's secondary action for either review or a simple close.
function handleCompletionSecondary() {
  if (completedOnOpen.value) {
    reviewCompletedCounts()
    return
  }
  completionMessageOpen.value = false
}

// Scroll the product below the sticky search card. Troubleshoot: refs, sticky offset, and nextTick.
async function scrollToProducts() {
  await nextTick()
  if (!findCard.value || !productStart.value) return
  if (window.matchMedia('(min-width: 768px) and (max-width: 1366px)').matches) {
    const headerHeight = Number.parseFloat(
      getComputedStyle(document.querySelector('.counter-shell')).getPropertyValue('--counter-header-height'),
    ) || 132
    const productTop = productStart.value.getBoundingClientRect().top + window.scrollY
    window.scrollTo({ top: Math.max(0, productTop - headerHeight - 12), behavior: 'auto' })
    return
  }
  const stickyTop = Number.parseFloat(getComputedStyle(findCard.value).top) || 0
  const productTop = productStart.value.getBoundingClientRect().top + window.scrollY
  const targetTop = productTop - stickyTop - findCard.value.offsetHeight - 12
  window.scrollTo({ top: Math.max(0, targetTop), behavior: 'auto' })
}

// Change the selected mobile product without requiring the current product to be saved first.
async function changeMobileRow(direction) {
  const nextIndex = Math.min(
    Math.max(0, mobileRowIndex.value + direction),
    Math.max(0, filtered.value.length - 1),
  )
  if (nextIndex === mobileRowIndex.value) return
  mobileRowIndex.value = nextIndex
  activeDetailId.value = null
  await scrollToProducts()
}

// Release the completed count lock after the counter confirms the next step.
async function selectAnotherCycleCount() {
  const currentRow = mobilePaginated.value[0]
  if (finishingCycleCount.value) return
  finishingCycleCount.value = true
  try {
    await releaseCounterSession(route.params.cycleCount)
    await router.push('/counter/cycle-counts')
  } catch (requestError) {
    currentRow._error = requestError.message
    completionMessageOpen.value = false
  } finally {
    finishingCycleCount.value = false
  }
}

// Navigate to a valid page and adjust scrolling. Troubleshoot: totalPages, currentPage, and the mobile breakpoint.
async function changePage(page) {
  const nextPage = Math.min(Math.max(1, page), totalPages.value)
  if (nextPage === currentPage.value) return
  currentPage.value = nextPage
  await nextTick()

  if (
    window.matchMedia('(max-width: 767px)').matches &&
    findCard.value &&
    productStart.value
  ) {
    await scrollToProducts()
    return
  }

  window.scrollTo({ top: 0, behavior: 'auto' })
}

// Display a placeholder for blank or null values. Troubleshoot: the raw field value returned by the API.
function display(value) {
  return value === null || value === undefined || value === '' ? '—' : value
}

// Format the quantity for display. Troubleshoot: numeric conversion and decimal rounding.
function quantity(value) {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 2 }) : value
}

// Format the last-counted timestamp using en-PH. Troubleshoot: valid API dates and browser timezone.
function countedAt(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('en-PH', {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  }).format(date)
}

// Check that the count is nonblank and a nonnegative whole number. Troubleshoot: the input value before saving.
function isValidCount(value) {
  return value !== '' && Number.isInteger(Number(value)) && Number(value) >= 0
}

// Calculate cases x qtyPerCase + pieces. Troubleshoot: actualCs, actualPc, and Qty/Case.
function actualTotal(row) {
  return (Number(row.actualCs || 0) * Number(row.qtyPerCase || 0)) + Number(row.actualPc || 0)
}

// Mark the row unsaved and clear the previous error. Troubleshoot: _dirty, _saved, and input events.
function markEdited(row) {
  row._dirty = true
  row._saved = false
  row._error = ''
}

// Replace an empty count with zero and mark the row edited. Troubleshoot: field name and blur/input binding.
function defaultEmptyCountToZero(row, field) {
  if (row[field] === '' || row[field] === null || row[field] === undefined) {
    row[field] = 0
    markEdited(row)
  }
}

// Validate and save the row, then apply the server values to the UI. Troubleshoot: row._error, token, and updateActualCount response.
async function saveActual(row) {
  if (!isValidCount(row.actualCs) || !isValidCount(row.actualPc)) {
    row._error = 'Enter whole numbers of zero or more for both fields.'
    return
  }

  row._saving = true
  row._error = ''
  try {
    const updated = await updateActualCount(
      row.detailId,
      Number(row.actualCs),
      Number(row.actualPc),
      counterSession.value?.token,
      route.params.cycleCount,
      {
        productionDate: row.productionDate,
        expiryDate: row.expiryDate,
        lotNo: row.lotNo,
      },
    )
    Object.assign(row, updated, {
      actualCs: Number(updated.finalCountCases),
      actualPc: Number(updated.finalCountPieces),
      _dirty: false,
      _saved: true,
      _saving: false,
      _error: '',
    })
    if (rows.value.every((product) => product._saved) && !completionPromptShown.value) {
      completionPromptShown.value = true
      completedOnOpen.value = false
      completionMessageOpen.value = true
    }
  } catch (requestError) {
    row._saving = false
    row._error = requestError.message
  }
}

// Load products and the header using the counter session. Troubleshoot: route ID, stored token, HTTP 403, and detail-field mapping.
async function loadDetails() {
  const loadingStartedAt = performance.now()
  loading.value = true
  error.value = ''
  completedOnOpen.value = false
  completionPromptShown.value = false
  completionMessageOpen.value = false
  const cycleCountId = route.params.cycleCount
  try {
    counterSession.value = JSON.parse(
      sessionStorage.getItem(`wms-counter-session-${cycleCountId}`),
    )
  } catch {
    counterSession.value = null
  }
  if (!counterSession.value?.token) {
    loading.value = false
    router.replace('/counter/cycle-counts')
    return
  }
  const handoff = consumeCountingHandoff(cycleCountId, counterSession.value.token)

  try {
    const details = handoff
      ? await handoff.details
      : await getCycleCountDetails(cycleCountId, counterSession.value.token)
    // Map API final counts into editable fields and row save/error flags. Troubleshoot: counterId and numeric conversions.
    rows.value = details.map((row) => ({
      ...row,
      actualCs: Number(row.finalCountCases || 0),
      actualPc: Number(row.finalCountPieces || 0),
      _dirty: false,
      _saved: Boolean(row.counterId),
      _saving: false,
      _error: '',
    }))
    currentPage.value = 1
    // Resume at the first product that still needs a count; completed counts reopen at the final product.
    const firstUncountedIndex = rows.value.findIndex((row) => !row._saved)
    mobileRowIndex.value = firstUncountedIndex >= 0
      ? firstUncountedIndex
      : Math.max(0, rows.value.length - 1)
    mobileListOpen.value = true
    // A reopened completed count starts with an explicit review-or-return choice.
    completedOnOpen.value = usesMobileProductFlow()
      && rows.value.length > 0
      && rows.value.every((row) => row._saved)
    completionPromptShown.value = completedOnOpen.value
    completionMessageOpen.value = completedOnOpen.value
  } catch (requestError) {
    if (requestError.status === 403) {
      sessionStorage.removeItem(`wms-counter-session-${cycleCountId}`)
      router.replace('/counter/cycle-counts')
      return
    }
    error.value = requestError.message
  } finally {
    const remainingLoadingTime = minimumLoadingTime - (performance.now() - loadingStartedAt)
    if (remainingLoadingTime > 0) {
      await new Promise((resolve) => window.setTimeout(resolve, remainingLoadingTime))
    }
    loading.value = false
  }

}

// Reload products when the cycleCount route ID changes; also run on initial load.
watch(() => route.params.cycleCount, loadDetails, { immediate: true })
// Return to the first page and product when the search or page size changes.
watch([query, pageSize], () => {
  currentPage.value = 1
  mobileRowIndex.value = 0
})
// Clamp the mobile product index when the filtered list becomes shorter.
watch(filtered, (products) => {
  if (mobileRowIndex.value >= products.length) mobileRowIndex.value = Math.max(0, products.length - 1)
})
// Clamp currentPage when totalPages decreases.
watch(totalPages, (pages) => {
  if (currentPage.value > pages) currentPage.value = pages
})
// On mount, apply page CSS classes to html/body. Troubleshoot: mobile sizing and scrolling.
onMounted(() => {
  document.documentElement.classList.add('mobile-counting-active')
  document.body.classList.add('mobile-counting-active')
})
// On unmount, remove page CSS classes and clear timers where applicable.
onBeforeUnmount(() => {
  document.documentElement.classList.remove('mobile-counting-active')
  document.body.classList.remove('mobile-counting-active')
})
</script>

<template>
  <main class="count-page">
    <section class="mapping-note card"><Info :size="18" /><p>Update the lot and dates when needed. Enter Actual CASE and Actual PC; Total updates automatically.</p></section>

    <section ref="findCard" :class="['find-card', 'card', { 'picker-search': mobileListOpen }]" aria-label="Search products">
      <button class="search-toggle" type="button" :aria-expanded="searchOpen" @click="searchOpen = !searchOpen"><span><Search :size="19" />Search products</span><ChevronDown :class="{ rotated: searchOpen }" :size="19" /></button>
      <div :class="['search-panel', { open: searchOpen }]">
        <div class="search-box"><Search :size="19" /><input v-model="query" type="search" inputmode="search" placeholder="Search product name" aria-label="Search product name" /></div>
      </div>
      <div class="results-row">
        <p class="results-summary desktop-results"><PackageSearch :size="15" />Showing {{ pageStart }}-{{ pageEnd }} of {{ filtered.length }} products<span v-if="filtered.length !== rows.length"> ({{ rows.length }} total)</span></p>
        <p class="results-summary mobile-results"><PackageSearch :size="15" />{{ mobileListOpen ? `${matchingProducts.length} product(s)` : `Product ${filtered.length ? mobileRowIndex + 1 : 0} of ${filtered.length}` }}</p>
        <span v-if="mobileListOpen" class="product-status-counters" aria-label="Filter products by count status">
          <button type="button" :class="['product-status-counter', 'all-products-counter', { active: productStatusFilter === 'all' }]" :aria-pressed="productStatusFilter === 'all'" :aria-label="`Show all ${matchingProducts.length} products`" title="Show all products" @click="productStatusFilter = 'all'">All {{ matchingProducts.length }}</button>
          <button type="button" :class="['product-status-counter', 'counted-counter', { active: productStatusFilter === 'counted' }]" :aria-pressed="productStatusFilter === 'counted'" :aria-label="`Show ${countedProductCount} counted products`" title="Counted products" @click="toggleProductStatusFilter('counted')"><Check :size="13" />{{ countedProductCount }}</button>
          <button type="button" :class="['product-status-counter', 'uncounted-counter', { active: productStatusFilter === 'uncounted' }]" :aria-pressed="productStatusFilter === 'uncounted'" :aria-label="`Show ${uncountedProductCount} not yet counted products`" title="Not yet counted products" @click="toggleProductStatusFilter('uncounted')"><PackageSearch :size="13" />{{ uncountedProductCount }}</button>
        </span>
        <label class="page-size">Rows per page<select v-model.number="pageSize" aria-label="Products per page"><option :value="1">1</option><option :value="5">5</option><option :value="10">10</option><option :value="20">20</option></select></label>
      </div>
    </section>

    <div ref="productStart" class="product-start" aria-hidden="true"></div>

    <section v-if="loading" class="state-card loading-state card" role="status" aria-live="polite">
      <span class="cycle-loader" aria-hidden="true"></span>
      <strong>Loading Cycle Count products…</strong>
      <span>Please wait while we prepare your product list.</span>
    </section>
    <section v-else-if="error" class="state-card card error-state"><AlertCircle :size="29" /><strong>Could not load database products</strong><span>{{ error }}</span><button class="btn btn-secondary" type="button" @click="loadDetails">Try again</button></section>

    <section v-else-if="filtered.length && mobileListOpen" class="product-picker" aria-label="Choose a product to count">
      <button v-for="(row, index) in filtered" :key="row.detailId" class="product-picker-row" type="button" @click="selectMobileProduct(index)">
        <span class="picker-top"><span class="picker-location"><MapPin :size="14" />{{ display(row.location) }}</span><span v-if="row._saved" class="picker-counted"><Check :size="14" />Counted</span></span>
        <small class="picker-item">{{ display(row.itemNumber) }}</small>
        <strong>{{ display(row.description) }}</strong>
      </button>
    </section>
    <section v-else-if="filtered.length" class="mobile-list" aria-label="Selected product in Cycle Count">
      <article
        v-for="row in mobilePaginated"
        :key="row.detailId"
        :class="['product-card', { 'active-product': activeDetailId === row.detailId, 'uncounted-product': !row.lastCountedBy }]"
      >
        <div class="card-top-actions"><button class="back-to-products" type="button" @click="showProductList"><ChevronLeft :size="16" />All products</button><span class="packing-inline"><component :is="packingIcon(row.packaging)" :size="17" />{{ display(row.packaging) }} · {{ display(row.unitsPerPack) }}/pack</span></div>
        <div class="product-heading"><span class="location"><MapPin :size="16" />{{ display(row.location) }}</span><span v-if="row._dirty" class="unsaved-status">Unsaved changes</span></div>
        <h2><Package :size="20" />{{ display(row.description) }}</h2>
        <p class="item-reference"><span>AI ID {{ display(row.activeInventoryId) }} · Detail {{ row.detailId }}</span></p>
        <p v-if="row.lastCountedBy" class="counted-by"><Check :size="14" aria-hidden="true" /><span>Counted by <strong>Counter No. {{ row.lastCountedBy }}</strong></span><small v-if="row.lastCountedAt" class="counted-at">{{ countedAt(row.lastCountedAt) }}</small></p>

        <dl class="primary-details">
          <div><dt><Tag :size="12" />Lot No.</dt><dd><input v-model="row.lotNo" class="metadata-input" type="text" maxlength="4000" placeholder="Enter lot no." aria-label="Lot number" :disabled="row._saving" @input="markEdited(row)" /></dd></div>
        </dl>
        <dl class="date-details">
          <div><dt><CalendarDays :size="12" />Production Date</dt><dd><input v-model="row.productionDate" class="metadata-input" type="date" aria-label="Production date" :disabled="row._saving" @change="markEdited(row)" /></dd></div>
          <div><dt><CalendarClock :size="12" />Expiration Date</dt><dd><input v-model="row.expiryDate" class="metadata-input" type="date" aria-label="Expiration date" :disabled="row._saving" @change="markEdited(row)" /></dd></div>
        </dl>

        <section class="actual-counts">
          <h3>Actual Count</h3>
          <div class="count-inputs">
            <label><span><Boxes :size="15" />Actual CASE</span><input v-model.number="row.actualCs" type="number" inputmode="numeric" pattern="[0-9]*" min="0" step="1" :aria-label="`Actual CASE for ${display(row.description)}`" :disabled="row._saving" @focus="activeDetailId = row.detailId" @input="markEdited(row)" @blur="defaultEmptyCountToZero(row, 'actualCs')" /></label>
            <label><span><PackageOpen :size="15" />Actual PC</span><input v-model.number="row.actualPc" type="number" inputmode="numeric" pattern="[0-9]*" min="0" step="1" :aria-label="`Actual PC for ${display(row.description)}`" :disabled="row._saving" @focus="activeDetailId = row.detailId" @input="markEdited(row)" @blur="defaultEmptyCountToZero(row, 'actualPc')" /></label>
          </div>
          <dl class="calculated-counts total-only">
            <div><dt>Total</dt><dd>{{ quantity(actualTotal(row)) }}</dd></div>
          </dl>
          <p v-if="row._error" class="row-error" role="alert">{{ row._error }}</p>
          <button :class="['save-count', { saved: row._saved }]" type="button" :disabled="row._saving || !row._dirty || connectionBlocked" @click="saveActual(row)"><Check v-if="row._saved" :size="20" /><Save v-else :size="19" />{{ connectionBlocked && row._dirty ? 'Waiting for connection' : row._saving ? 'Saving…' : row._saved ? 'Count saved' : 'Save actual count' }}</button>
        </section>
      </article>
    </section>

    <nav v-if="!loading && !error && filtered.length && !mobileListOpen" class="mobile-navigation card" aria-label="Mobile product navigation">
      <button type="button" :disabled="mobileRowIndex === 0" @click="changeMobileRow(-1)"><ChevronLeft :size="19" />Previous</button>
      <button
        type="button"
        :disabled="mobileRowIndex === filtered.length - 1"
        @click="changeMobileRow(1)"
      >
        Next<ChevronRight :size="19" />
      </button>
    </nav>

    <Teleport to="body">
      <Transition name="completion-fade">
        <div v-if="completionMessageOpen" class="completion-backdrop" aria-hidden="true"></div>
      </Transition>
      <Transition name="completion-pop">
        <section v-if="completionMessageOpen" class="next-navigation-modal completion-message" role="dialog" aria-modal="true" aria-labelledby="completion-title">
          <CircleCheckBig class="completion-icon" :size="42" aria-hidden="true" />
          <span id="completion-title" class="completion-copy">
            <template v-if="completedOnOpen">
              All products have already been counted.
              <strong>Awaiting posting by the Warehouse Manager. You can still review or correct the saved counts.</strong>
            </template>
            <template v-else>
              You have finished counting all products in this Cycle Count.
              <strong>It will remain available for review until the manager posts it.</strong>
            </template>
          </span>
          <div class="completion-actions">
            <button class="completion-back" type="button" :disabled="finishingCycleCount" @click="handleCompletionSecondary">{{ completedOnOpen ? 'Review Counts' : 'Back' }}</button>
            <button type="button" :disabled="finishingCycleCount" @click="selectAnotherCycleCount">
              {{ finishingCycleCount ? 'Opening…' : 'Cycle Counts' }}
            </button>
          </div>
        </section>
      </Transition>
    </Teleport>

    <section v-if="!loading && !error && filtered.length" class="desktop-table card" aria-label="Products in Cycle Count">
      <div class="table-scroll" tabindex="0" aria-label="Cycle Count products; scroll horizontally for more columns">
        <table>
          <colgroup><col class="col-detail"><col class="col-ai"><col class="col-location"><col class="col-description"><col class="col-date"><col class="col-date"><col class="col-lot"><col class="col-qty"><col class="col-old"><col class="col-count"><col class="col-count"><col class="col-total"><col class="col-action"></colgroup>
          <thead><tr><th>Detail ID</th><th>AI ID</th><th>Location</th><th>Description</th><th>Production Date</th><th>Expiration Date</th><th>Lot No.</th><th>Qty/Case</th><th>Old Count</th><th>Actual C</th><th>Actual PC</th><th>Actual Total</th><th>Action</th></tr></thead>
          <tbody><tr v-for="row in paginated" :key="row.detailId"><td>{{ row.detailId }}</td><td>{{ display(row.activeInventoryId) }}</td><td><strong>{{ display(row.location) }}</strong></td><td class="description" :title="display(row.description)">{{ display(row.description) }}<span v-if="row.lastCountedBy" class="table-counted-by"><Check :size="13" aria-hidden="true" /><span>Counted by <strong>Counter No. {{ row.lastCountedBy }}</strong></span></span></td><td><input v-model="row.productionDate" class="table-metadata-input" type="date" aria-label="Production date" :disabled="row._saving" @change="markEdited(row)" /></td><td><input v-model="row.expiryDate" class="table-metadata-input" type="date" aria-label="Expiration date" :disabled="row._saving" @change="markEdited(row)" /></td><td><input v-model="row.lotNo" class="table-metadata-input" type="text" maxlength="4000" placeholder="Lot No." aria-label="Lot number" :disabled="row._saving" @input="markEdited(row)" /></td><td>{{ quantity(row.qtyPerCase) }}</td><td class="old-count-cell">{{ quantity(row.oldQty) }}</td><td class="actual-cell"><input v-model.number="row.actualCs" class="table-input" type="number" inputmode="numeric" min="0" step="1" :aria-label="`Actual CASE for ${display(row.description)}`" :disabled="row._saving" @input="markEdited(row)" @blur="defaultEmptyCountToZero(row, 'actualCs')" /></td><td class="actual-cell"><input v-model.number="row.actualPc" class="table-input" type="number" inputmode="numeric" min="0" step="1" :aria-label="`Actual PC for ${display(row.description)}`" :disabled="row._saving" @input="markEdited(row)" @blur="defaultEmptyCountToZero(row, 'actualPc')" /></td><td class="actual-cell">{{ quantity(actualTotal(row)) }}</td><td><button :class="['table-save', { saved: row._saved }]" type="button" :disabled="row._saving || !row._dirty || connectionBlocked" @click="saveActual(row)">{{ connectionBlocked && row._dirty ? 'Offline' : row._saving ? 'Saving…' : row._saved ? 'Saved' : 'Save' }}</button><small v-if="row._error" class="table-error">{{ row._error }}</small></td></tr></tbody>
        </table>
      </div>
    </section>

    <nav v-if="!loading && !error && filtered.length" class="pagination card" aria-label="Product pages">
      <button type="button" :disabled="currentPage === 1" aria-label="Previous page" @click="changePage(currentPage - 1)"><ChevronLeft :size="19" />Previous</button>
      <span>Page <strong>{{ currentPage }}</strong> of <strong>{{ totalPages }}</strong></span>
      <button type="button" :disabled="currentPage === totalPages" aria-label="Next page" @click="changePage(currentPage + 1)">Next<ChevronRight :size="19" /></button>
    </nav>

    <section v-if="!loading && !error && !filtered.length" class="state-card card"><PackageSearch :size="29" /><strong>{{ rows.length ? 'No products found' : 'This Cycle Count has no detail records' }}</strong><span v-if="rows.length">Try searching for a different product name.</span></section>
  </main>
</template>

<style scoped>
.count-page{width:min(1600px,100%);margin:0 auto;padding:20px 24px 42px}.mapping-note{display:flex;align-items:flex-start;gap:9px;padding:12px 14px;margin-bottom:12px;background:#fffbeb;border-color:#fde68a;color:#78350f}.mapping-note svg{flex:0 0 auto}.mapping-note p{margin:0;font-size:13px;line-height:1.5}.find-card{padding:10px 12px;margin-bottom:16px}.search-toggle{display:none}.search-panel{display:block}.search-box{position:relative}.search-box svg{position:absolute;left:11px;top:50%;transform:translateY(-50%);color:#64748b}.search-box input{width:100%;min-height:38px;border:1px solid #d8e0d9;border-radius:8px;padding:7px 11px 7px 36px;background:#fff;color:#0f172a;font-size:13px}.search-box input:focus{border-color:#15803d;outline:3px solid rgba(21,128,61,.12)}.results-summary{display:flex;align-items:center;gap:6px;margin:10px 0 0;color:#64748b;font-size:12px}.mobile-results,.mobile-navigation{display:none}.mobile-list{display:none}.desktop-table{overflow:hidden}.table-scroll{max-width:100%;overflow-x:auto}.desktop-table table{min-width:1650px}.desktop-table th,.desktop-table td{padding:9px 8px;font-size:11px}.desktop-table .description{min-width:240px;font-weight:800}.old-count-cell{background:#ffcc67;font-weight:900}.actual-cell{background:#e5ffd2;font-weight:800}.table-input{width:70px;min-height:42px;border:2px solid #86c995;border-radius:7px;background:#fff;text-align:center;font-size:16px;font-weight:900;color:#14532d}.table-input:focus{outline:3px solid rgba(21,128,61,.13);border-color:#15803d}.table-save{min-width:68px;min-height:42px;border:0;border-radius:8px;background:#166534;color:#fff;font-weight:900}.table-save:disabled{opacity:.5}.table-save.saved:disabled{opacity:1;background:#dcfce7;color:#166534}.table-error{display:block;width:130px;margin-top:5px;color:#b91c1c}.state-card{min-height:220px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;padding:24px;text-align:center;color:#64748b}.state-card strong{color:#334155}.error-state svg{color:#b91c1c}
.table-metadata-input{width:100%;min-width:105px;min-height:38px;padding:5px 7px;border:1px solid #86c995;border-radius:7px;background:#fff;color:#14532d;font-size:12px;font-weight:800;text-align:center}.table-metadata-input:focus{border-color:#15803d;outline:3px solid rgba(21,128,61,.12)}
.loading-state{gap:11px}.loading-state>span:last-child{font-size:12px}.cycle-loader{width:48px;height:48px;margin-bottom:3px;border:5px solid #d8eee0;border-top-color:#15803d;border-right-color:#22c55e;border-radius:50%;box-shadow:0 0 0 6px rgba(22,163,74,.06);animation:cycle-loader-spin .75s linear infinite}@keyframes cycle-loader-spin{to{transform:rotate(360deg)}}@keyframes content-reveal{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}.product-picker,.mobile-list,.desktop-table{animation:content-reveal .24s ease-out both}
.product-status-counters{display:none;align-items:center;gap:5px}.product-status-counter{min-width:36px;height:28px;padding:0 7px;border:1px solid transparent;border-radius:999px;align-items:center;justify-content:center;gap:4px;font-size:11px;font-weight:900}.product-status-counter.active{border-color:#15803d;box-shadow:0 0 0 2px rgba(21,128,61,.13)}.counted-counter{background:#dcfce7;color:#166534}.uncounted-counter{background:#fef3c7;color:#92400e}
.item-reference{display:flex;align-items:center;justify-content:space-between;gap:8px}.packing-inline{flex:0 0 auto;display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;background:#f0fdf4;color:#166534;font-size:13px;font-weight:900;white-space:nowrap}.actual-counts .calculated-counts.total-only{grid-template-columns:1fr}.count-inputs input:invalid,.table-input:invalid{border-color:#dc2626;background:#fff7f7;color:#991b1b}
@media(max-width:1366px){.count-page{padding:12px 12px 32px}.mapping-note p{font-size:12px}.find-card{position:sticky;top:var(--counter-header-height,170px);z-index:15;padding:0;margin-bottom:18px;overflow:hidden;box-shadow:0 0 0 6px #f4f7f4,0 8px 20px rgba(15,23,42,.13)}.search-toggle{width:100%;min-height:48px;border:0;background:#fff;color:#334155;padding:0 14px;display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:14px;font-weight:900}.search-toggle>span{display:flex;align-items:center;gap:7px}.search-toggle svg{transition:transform .2s ease}.search-toggle svg.rotated{transform:rotate(180deg)}.search-panel{display:none;border-top:1px solid #edf1ed;padding:12px}.search-panel.open{display:block}.results-summary{border-top:1px solid #edf1ed;padding:9px 12px;margin:0}.mobile-list{display:grid;gap:12px}.desktop-table{display:none}.product-card{min-width:0;background:#fff;border:1px solid #dfe6e0;border-left:5px solid #15803d;border-radius:15px;padding:15px;box-shadow:0 5px 18px rgba(15,23,42,.05)}.product-heading{display:flex;align-items:center;justify-content:space-between;gap:8px}.location{display:flex;align-items:center;gap:5px;color:#14532d;font-size:13px;font-weight:900}.product-card h2{display:flex;align-items:flex-start;gap:6px;font-size:18px;line-height:1.3;margin:12px 0 3px;color:#17211b;overflow-wrap:anywhere}.product-card h2 svg{flex:0 0 auto}.item-reference{margin:0 0 11px;color:#64748b;font-size:11px}.primary-details,.date-details{display:grid;margin:0}.primary-details{grid-template-columns:repeat(2,minmax(0,1fr));border:1px solid #e6ebe7;border-radius:10px;background:#fafcfa}.primary-details>div{min-width:0;padding:10px;border-right:1px solid #e6ebe7}.primary-details>div:last-child{border:0}.date-details{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:8px}.date-details>div{padding:8px 10px;background:#f7f9f7;border-radius:9px}.product-card dt{display:flex;align-items:center;gap:4px;color:#64748b;font-size:10px;text-transform:uppercase;font-weight:800}.product-card dd{margin:3px 0 0;color:#1e293b;font-size:14px;font-weight:900;overflow-wrap:anywhere}.actual-counts{margin-top:12px;border:1px solid #bae6c3;border-radius:10px;overflow:hidden}.actual-counts h3{display:flex;justify-content:space-between;align-items:center;margin:0;padding:8px 10px;background:#eaf8ed;color:#166534;font-size:13px}.count-inputs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;padding:10px}.count-inputs label>span{display:flex;align-items:center;gap:5px;margin-bottom:5px;color:#334155;font-size:12px;font-weight:900}.count-inputs input{width:100%;height:58px;border:2px solid #86c995;border-radius:10px;background:#fff;text-align:center;font-size:24px;font-weight:900;color:#14532d;-moz-appearance:textfield}.count-inputs input::-webkit-inner-spin-button,.count-inputs input::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}.count-inputs input:focus{outline:3px solid rgba(21,128,61,.13);border-color:#15803d}.actual-counts .calculated-counts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));margin:0;border-top:1px solid #e3eee5}.calculated-counts>div{padding:9px;text-align:center}.calculated-counts>div+div{border-left:1px solid #e3eee5}.actual-counts dt{justify-content:center}.actual-counts dd{font-size:18px;color:#166534}.row-error{margin:0;padding:8px 10px;color:#b91c1c;font-size:12px;font-weight:800}.save-count{width:calc(100% - 20px);min-height:50px;margin:0 10px 10px;border:0;border-radius:10px;background:#166534;color:#fff;display:flex;align-items:center;justify-content:center;gap:6px;font-size:15px;font-weight:900}.save-count:disabled{opacity:.5}.save-count.saved:disabled{opacity:1;background:#dcfce7;color:#166534}.state-card{min-height:180px}}
.product-card{transition:border-color .18s ease,background-color .18s ease,box-shadow .18s ease,transform .18s ease}.product-card.active-product{border-color:#16a34a;border-left-width:8px;background:#f0fdf4;box-shadow:0 0 0 3px rgba(22,163,74,.2),0 10px 26px rgba(15,23,42,.12);transform:translateX(2px)}
@media(max-width:350px){.count-page{padding-left:8px;padding-right:8px}.product-card{padding:12px}.primary-details{grid-template-columns:repeat(2,minmax(0,1fr))}.primary-details .old-count{grid-column:1/-1;border-top:1px solid #e6ebe7;border-radius:0 0 9px 9px}.primary-details>div:nth-child(2){border-right:0}.actual-counts dl>div{padding:8px 2px}.actual-counts dd{font-size:15px}}

/* Readable desktop raw-data table. Scroll horizontally instead of shrinking text. */
.results-row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:10px}.results-row .results-summary{margin:0}.page-size{display:flex;align-items:center;gap:7px;color:#64748b;font-size:12px;font-weight:800}.page-size select{min-height:36px;border:1px solid #d8e0d9;border-radius:8px;background:#fff;padding:0 8px;color:#334155;font-size:14px}.table-scroll{overflow-x:auto}.desktop-table table{width:100%;min-width:1420px;table-layout:auto}.desktop-table th,.desktop-table td{padding:10px 9px;font-size:12px;line-height:1.4;vertical-align:middle;white-space:nowrap}.desktop-table th{font-size:11px}.desktop-table .description{width:220px;min-width:220px;max-width:220px;white-space:normal;overflow-wrap:anywhere}.col-detail{width:85px}.col-ai{width:100px}.col-location{width:100px}.col-description{width:220px}.col-date{width:125px}.col-lot{width:120px}.col-qty{width:90px}.col-old{width:100px}.col-count{width:95px}.col-total{width:105px}.col-variance{width:95px}.col-action{width:100px}.table-input{width:82px;min-width:82px;padding:4px}.table-save{min-width:76px;padding:6px;font-size:12px}.table-error{width:140px;overflow-wrap:anywhere}.pagination{display:flex;align-items:center;justify-content:center;gap:16px;margin-top:14px;padding:10px 14px;color:#475569;font-size:13px}.pagination button{min-height:44px;padding:0 14px;border:1px solid #cfd9d1;border-radius:9px;background:#fff;color:#166534;display:flex;align-items:center;justify-content:center;gap:4px;font-weight:900}.pagination button:hover:not(:disabled){background:#f0fdf4;border-color:#86c995}.pagination button:disabled{opacity:.42;cursor:not-allowed}
.desktop-table table{min-width:1420px}.desktop-table .description{width:220px;min-width:220px;max-width:220px;overflow-wrap:anywhere}.col-description{width:220px}
@media(min-width:1440px){.desktop-table table{min-width:0;table-layout:fixed}.desktop-table th,.desktop-table td{padding:9px 6px;font-size:clamp(10px,.72vw,12px)}.desktop-table th{font-size:clamp(10px,.67vw,11px)}.desktop-table .description{width:auto;min-width:0;max-width:none}.table-input{width:100%;min-width:0}.table-save{width:100%;min-width:0}.col-detail{width:4%}.col-ai{width:5%}.col-location{width:6%}.col-description{width:16%}.col-date{width:8%}.col-lot{width:8%}.col-qty{width:6%}.col-old{width:7%}.col-count{width:7%}.col-total{width:7%}.col-variance{width:6%}.col-action{width:8%}}
@media(min-width:1100px) and (max-width:1439px){.count-page{padding-left:14px;padding-right:14px}.desktop-table table{min-width:1200px}.desktop-table th,.desktop-table td{padding:8px 6px;font-size:11px}.desktop-table th{font-size:10px}.desktop-table .description{width:190px;min-width:190px;max-width:190px}.table-input{width:74px;min-width:74px}.table-save{min-width:68px;font-size:11px}}
@media(min-width:768px) and (max-width:1099px){.count-page{padding-left:12px;padding-right:12px}.desktop-table table{min-width:1120px}.desktop-table th,.desktop-table td{padding:7px 5px;font-size:10px}.desktop-table th{font-size:9px}.desktop-table .description{min-width:210px}.table-input{width:68px;min-width:68px}.table-save{min-width:64px;font-size:10px}}
.desktop-table thead th{position:sticky;top:0;z-index:4;background:#f1f7f2;box-shadow:0 2px 4px rgba(15,23,42,.09)}

@media(max-width:1366px){.search-toggle{min-height:44px;padding-left:12px;padding-right:12px}.results-row{display:flex;border-top:1px solid #edf1ed;padding:6px 10px;margin:0}.results-row .results-summary{min-width:0;flex:1;border:0;padding:0;font-size:10px;line-height:1.25}.desktop-results,.page-size,.pagination{display:none}.mobile-results,.product-status-counters{display:flex}.mobile-navigation{display:flex;align-items:center;justify-content:center;gap:10px;margin-top:12px;padding:10px}.mobile-navigation button{min-height:48px;padding:0 16px;border:1px solid #86c995;border-radius:10px;background:#166534;color:#fff;display:flex;align-items:center;justify-content:center;gap:4px;font-weight:900}.mobile-navigation button:disabled{border-color:#d8e0d9;background:#e5e7eb;color:#94a3b8;cursor:not-allowed}}
@media(max-width:1366px){.search-toggle,.search-panel,.search-panel.open{display:none}.results-row{border-top:0}}
@media(max-width:1366px){.date-details input[type="date"]{text-align:center;line-height:normal}.date-details input[type="date"]::-webkit-date-and-time-value{display:flex;min-width:100%;height:100%;align-items:center;justify-content:center;text-align:center}.date-details input[type="date"]::-webkit-datetime-edit{display:flex;height:100%;align-items:center;justify-content:center}}

/* Roomier type and controls for tablet and iPad card counting views. */
@media(min-width:768px) and (max-width:1366px){
  :global(html.mobile-counting-active),:global(body.mobile-counting-active),:global(html.mobile-counting-active #app){height:auto;min-height:100%;overflow-y:auto}
  .count-page{width:min(920px,100%);padding:18px 20px 28px}
  .find-card{position:static;top:auto;box-shadow:none}.mobile-list{overflow:visible}
  .mapping-note{padding:12px 15px}.mapping-note p{font-size:14px;line-height:1.45}
  .find-card{margin-bottom:14px}.results-row{padding:10px 14px}.results-row .results-summary{font-size:13px}
  .product-card{padding:20px;border-radius:17px}
  .location{font-size:16px}.detail-id{font-size:12px}
  .product-card h2{margin:12px 0 5px;font-size:27px;line-height:1.2}
  .product-card h2 svg{width:26px;height:26px}.item-reference{margin-bottom:12px;font-size:13px}
  .counted-by{padding:8px 10px;font-size:13px}.counted-by strong{font-size:14px}.counted-by small{font-size:11px}
  .primary-details{width:calc(50% - 5.5px);margin-inline:auto;grid-template-columns:1fr}
  .primary-details>div,.date-details>div{padding:13px 14px}.primary-details>div{border-right:0}.date-details{gap:11px;margin-top:11px}
  .primary-details dt,.primary-details dd,.date-details dt,.date-details dd{justify-content:center;text-align:center}
  .product-card dt{font-size:12px}.product-card dd{font-size:17px}.metadata-input{display:block;width:100%;min-width:0;height:46px;border:1px solid #86c995;border-radius:8px;background:#fff;padding:5px 8px;color:#14532d;font-size:14px;font-weight:800;text-align:center}
  .actual-counts{margin-top:14px}.actual-counts h3{padding:11px 13px;font-size:16px}.actual-counts h3 small{font-size:11px}
  .count-inputs{gap:12px;padding:13px}.count-inputs label>span{margin-bottom:7px;font-size:14px}
  .count-inputs input{height:68px;font-size:31px}.calculated-counts>div{padding:11px}.actual-counts dd{font-size:22px}
  .save-count{min-height:56px;font-size:17px}
  .mobile-navigation{gap:14px;padding:10px}.mobile-navigation button{min-height:50px;padding:0 22px;font-size:15px}
}

/* Compact mobile counter layout so the active product and actions fit together. */
@media(max-width:767px){
  .count-page{padding:7px 8px 18px}
  .mapping-note{padding:6px 8px;margin-bottom:6px;gap:6px}
  .mapping-note svg{width:14px;height:14px}
  .mapping-note p{font-size:11px;line-height:1.25}
  .find-card{position:static;margin-bottom:10px;box-shadow:none}
  .search-toggle,.search-panel,.search-panel.open{display:none}
  .results-row{padding:4px 8px}
  .results-row .results-summary{font-size:11px}
  .product-card{padding:14px 15px;border-radius:14px}
  .product-card h2{margin:9px 0 3px;font-size:18px;line-height:1.25}
  .product-card h2 svg{width:19px;height:19px}
  .location{font-size:14px}
  .detail-id{font-size:11px}
  .item-reference{margin-bottom:7px;font-size:11px}
  .counted-by{margin-bottom:5px;padding:3px 6px;font-size:10px}
  .counted-by strong{font-size:11px}
  .primary-details{grid-template-columns:1fr}
  .primary-details>div{padding:9px 10px}
  .date-details{gap:5px;margin-top:5px}
  .date-details>div{padding:8px 9px}
  .product-card dt{font-size:10px}
  .product-card dd{margin-top:2px;font-size:15px}
  .metadata-input{width:100%;min-width:0;height:34px;border:1px solid #86c995;border-radius:6px;background:#fff;padding:3px 6px;color:#14532d;font-size:13px;font-weight:800;text-align:center}
  .metadata-input:focus{border-color:#15803d;outline:2px solid rgba(21,128,61,.14)}
  .actual-counts{margin-top:8px}
  .actual-counts h3{padding:6px 9px;font-size:13px}
  .actual-counts h3 small{font-size:9px}
  .count-inputs{gap:6px;padding:6px 8px}
  .count-inputs label>span{margin-bottom:3px;font-size:11px}
  .count-inputs input{height:54px;font-size:24px}
  .calculated-counts>div{padding:5px}
  .actual-counts dd{font-size:15px}
  .save-count{width:calc(100% - 16px);min-height:44px;margin:0 8px 7px;font-size:14px}
  .mobile-navigation{justify-content:center;gap:8px;margin-top:6px;padding:5px}
  .mobile-navigation button{min-height:34px;padding:0 9px;border-radius:7px;font-size:11px}
  .mobile-navigation button svg{width:15px;height:15px}
}

@media(min-width:768px) and (max-width:1100px){.count-page{padding-left:12px;padding-right:12px}.desktop-table th,.desktop-table td{padding-left:2px;padding-right:2px;font-size:9px}.table-input{font-size:14px}.table-save{font-size:9px}}
/* Laptop-sized screens with a mouse or trackpad use the desktop raw-data table.
   Touch tablets keep the card layout in both portrait and landscape orientations. */
@media(min-width:768px) and (max-width:1366px) and (hover:hover) and (pointer:fine){
  .count-page{width:min(1600px,100%);padding:20px 14px 42px}
  .mobile-list,.mobile-results,.mobile-navigation,.product-status-counters{display:none}
  .desktop-table{display:block}
  .desktop-results{display:flex}
  .page-size{display:flex}
  .pagination{display:flex}
  .find-card{position:static;top:auto;margin-bottom:16px;box-shadow:none}
  .results-row{display:flex;border-top:1px solid #edf1ed;padding:0;margin-top:10px}
  .results-row .results-summary{font-size:12px}
}
.counted-by,.table-counted-by{display:flex;width:fit-content;max-width:100%;align-items:center;gap:5px;padding:5px 8px;border:1px solid #86c995;border-radius:6px;background:#dcfce7;color:#14532d;font-size:11px;font-weight:700;line-height:1.4}.counted-by{width:100%;margin:0 0 9px}.counted-by>svg,.table-counted-by>svg{flex-shrink:0}.counted-by>span,.table-counted-by>span{min-width:0;overflow-wrap:anywhere}.counted-by>span{flex:1}.counted-by strong,.table-counted-by strong{display:inline;margin-left:4px;font-size:12px;font-weight:800}.counted-by small,.table-counted-by small{display:block;margin-top:1px;color:#3f6650;font-size:9px;font-weight:800}.counted-by .counted-at{flex:0 0 auto;margin:0 0 0 auto;text-align:right;white-space:nowrap}.table-counted-by{margin-top:5px;padding:4px 6px;font-size:10px}.table-counted-by strong{font-size:11px}
.unsaved-status{padding:4px 7px;border-radius:999px;background:#fef3c7;color:#92400e;font-size:10px;font-weight:900;white-space:nowrap}.metadata-input:disabled,.table-metadata-input:disabled{background:#f1f5f2;color:#64748b}.table-scroll:focus-visible{outline-offset:-3px}
.next-navigation-modal{position:fixed;z-index:120;right:16px;bottom:82px;left:16px;display:flex;align-items:center;justify-content:center;gap:8px;margin:auto;padding:13px 15px;border:1px solid #fcd34d;border-radius:12px;background:#fffbeb;color:#92400e;box-shadow:0 12px 30px rgba(15,23,42,.2);font-size:13px;font-weight:800;text-align:center}
.completion-backdrop{position:fixed;z-index:119;inset:0;background:rgba(15,23,42,.16);-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}
.next-navigation-modal.completion-message{top:50%;bottom:auto;width:min(520px,calc(100% - 28px));min-height:210px;padding:28px 24px;flex-direction:column;gap:18px;transform:translateY(-50%);border-color:#dce5de;border-radius:16px;background:#fff;color:#183d24;box-shadow:0 18px 48px rgba(15,23,42,.24);font-size:16px;line-height:1.5}
.completion-icon{flex:0 0 auto;color:#15803d}
.completion-copy{color:#334155}.completion-copy strong{color:#15803d;font-weight:900}
.completion-actions{display:flex;width:100%;gap:10px}.completion-message button{flex:1;min-height:48px;padding:0 16px;border:1px solid #166534;border-radius:9px;background:#166534;color:#fff;font:inherit;white-space:nowrap}.completion-message button.completion-back{border-color:#cbd5e1;background:#fff;color:#334155}.completion-message button:disabled{opacity:.65;cursor:wait}
.completion-fade-enter-active,.completion-fade-leave-active{transition:opacity .22s ease}.completion-fade-enter-from,.completion-fade-leave-to{opacity:0}.completion-pop-enter-active{transition:opacity .24s ease,transform .24s cubic-bezier(.2,.8,.2,1)}.completion-pop-leave-active{transition:opacity .18s ease,transform .18s ease}.completion-pop-enter-from,.completion-pop-leave-to{opacity:0;transform:translateY(-48%) scale(.96)}
@media(max-width:767px){:global(html.mobile-counting-active),:global(body.mobile-counting-active),:global(html.mobile-counting-active #app){height:100%;min-height:0;overflow:hidden}.next-navigation-modal{bottom:calc(58px + env(safe-area-inset-bottom));font-size:12px}.count-page{height:auto;max-height:none;min-height:0;flex:1 1 auto;display:flex;flex-direction:column;padding:6px calc(8px + env(safe-area-inset-right)) env(safe-area-inset-bottom) calc(8px + env(safe-area-inset-left));overflow:hidden}.mapping-note{flex:0 0 auto;padding:6px 9px;margin-bottom:5px}.mapping-note p{font-size:10px;line-height:1.25}.mapping-note svg{width:14px;height:14px}.find-card{flex:0 0 auto;margin-bottom:6px}.results-row{padding:5px 9px}.results-row .results-summary{font-size:10px}.mobile-list{display:flex;flex:1 1 auto;min-height:0;margin:0 0 6px;overflow:visible}.mobile-list .product-card,.mobile-list .product-card.uncounted-product{min-height:0;flex:1;padding:12px 13px;border-radius:12px;overflow:visible}.product-heading{min-height:21px}.product-card h2{margin:8px 0 3px;font-size:20px;line-height:1.18}.product-card h2 svg{width:20px;height:20px}.location{font-size:14px}.detail-id{font-size:10px}.item-reference{margin-bottom:6px;font-size:10px;line-height:1.25}.counted-by{margin-bottom:6px;padding:5px 7px;font-size:10px;line-height:1.25}.counted-by strong{font-size:11px}.counted-by .counted-at{font-size:9px}.primary-details>div{padding:8px 9px}.date-details{gap:6px;margin-top:6px}.date-details>div{padding:7px 8px}.product-card dt{font-size:10px}.metadata-input{height:42px;padding:4px 7px;font-size:13px}.actual-counts{margin-top:7px}.actual-counts h3{padding:7px 8px;font-size:12px}.actual-counts h3 small{font-size:9px}.count-inputs{gap:7px;padding:7px 8px}.count-inputs label>span{margin-bottom:4px;font-size:11px}.count-inputs input{height:58px;font-size:25px}.calculated-counts>div{padding:7px 4px}.actual-counts dd{font-size:16px}.save-count{width:calc(100% - 16px);min-height:48px;margin:0 8px 8px;font-size:14px}.mobile-navigation{flex:0 0 auto;justify-content:center;gap:9px;margin:0;padding:6px}.mobile-navigation button{min-height:42px;padding:0 13px;border-radius:8px;font-size:12px}.mobile-navigation button svg{width:15px;height:15px}}
@media(max-width:767px){.product-card h2{font-size:21px}.product-card h2 svg{width:21px;height:21px}.date-details .metadata-input{display:block;min-width:0;white-space:nowrap;font-size:12px;letter-spacing:-.15px;padding-left:4px;padding-right:3px}}
@media(max-width:767px){.date-details dt{justify-content:center;text-align:center}.date-details dd{text-align:center}.date-details input[type="date"]{margin-inline:auto;text-align:center}.date-details input[type="date"]::-webkit-date-and-time-value{min-width:100%;text-align:center}}
@media(max-width:767px) and (max-height:820px){.count-page{padding-top:4px}.mapping-note{padding:4px 7px;margin-bottom:4px}.mapping-note p{line-height:1.15}.find-card{margin-bottom:4px}.results-row{padding:4px 8px}.mobile-list{margin-bottom:4px}.mobile-list .product-card,.mobile-list .product-card.uncounted-product{padding:10px 11px}.product-heading{min-height:19px}.product-card h2{margin:6px 0 2px}.item-reference{margin-bottom:4px}.counted-by{margin-bottom:4px;padding:3px 6px}.primary-details>div{padding:6px 7px}.date-details{gap:5px;margin-top:4px}.date-details>div{padding:5px 6px}.metadata-input{height:38px}.actual-counts{margin-top:5px}.actual-counts h3{padding:5px 7px}.count-inputs{padding:5px 7px}.count-inputs input{height:52px;font-size:23px}.calculated-counts>div{padding:5px 4px}.save-count{min-height:43px;margin-bottom:6px}.mobile-navigation{padding:5px}.mobile-navigation button{min-height:40px}}
@media(max-width:767px) and (max-height:700px){.count-page{padding-top:3px}.mapping-note{padding:3px 6px;margin-bottom:3px}.mapping-note p{font-size:9px}.find-card{margin-bottom:3px}.results-row{padding:3px 7px}.mobile-list{margin-bottom:3px}.mobile-list .product-card,.mobile-list .product-card.uncounted-product{padding:8px 9px}.product-card h2{margin-top:4px;font-size:19px}.item-reference{margin-bottom:3px}.counted-by{margin-bottom:3px;padding:2px 5px}.primary-details>div{padding:4px 6px}.date-details{margin-top:3px}.date-details>div{padding:4px 5px}.metadata-input{height:34px}.actual-counts{margin-top:4px}.actual-counts h3{padding:4px 6px}.count-inputs{padding:4px 6px}.count-inputs input{height:46px;font-size:21px}.calculated-counts>div{padding:3px}.save-count{min-height:38px;margin-bottom:5px}.mobile-navigation{padding:4px}.mobile-navigation button{min-height:38px}}
@media(max-width:767px){.item-reference{gap:5px}.item-reference>span:first-child{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.packing-inline{font-size:12px}}
@media(max-width:767px){.card-top-actions{margin-bottom:2px}.mobile-list .product-card h2{margin-top:3px}.mobile-list .product-card .item-reference{margin-bottom:1px}.mobile-list .product-card .counted-by{margin-bottom:2px}.mobile-list .product-card .date-details{margin-top:2px}.mobile-list .product-card .actual-counts{margin-top:3px}}
.product-picker{display:none}
@media(max-width:1366px){
  .find-card.picker-search{display:block;padding:10px 12px;margin-bottom:10px}
  .find-card.picker-search .search-panel{display:block;border:0;padding:0}
  .find-card.picker-search .results-row{padding:7px 2px 0}
  .product-picker{display:flex;flex:1 1 auto;flex-direction:column;gap:8px;min-height:0;overflow-y:auto;padding:2px 2px 12px}
  .product-picker-row{position:relative;width:100%;min-height:88px;padding:14px 15px;border:1px solid #dce5de;border-left:4px solid #15803d;border-radius:11px;background:#fff;color:#1e293b;text-align:left;box-shadow:0 3px 10px rgba(15,23,42,.04)}
  .product-picker-row strong{display:block;margin-top:5px;font-size:15px;line-height:1.35}
  .picker-item{display:block;width:max-content;max-width:100%;margin-top:6px;overflow:hidden;color:#64748b;font-size:11px;font-weight:800;text-overflow:ellipsis;white-space:nowrap}
  .picker-top{display:flex;align-items:center;justify-content:space-between;gap:10px}
  .picker-location{display:inline-flex;align-items:center;gap:4px;color:#166534;font-size:12px;font-weight:900}
  .picker-counted{display:inline-flex;align-items:center;gap:4px;color:#15803d;font-size:11px;font-weight:900}
  .back-to-products{display:inline-flex;align-items:center;gap:4px;margin:0 0 8px;padding:5px 8px;border:1px solid #dce5de;border-radius:7px;background:#fff;color:#166534;font-size:11px;font-weight:900}
  .card-top-actions{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}.card-top-actions .back-to-products{margin:0}.card-top-actions .packing-inline{align-self:flex-start;margin-top:-3px}
}
@media(min-width:768px) and (max-width:1366px) and (hover:hover) and (pointer:fine){.product-picker{display:none}.search-panel{display:block}.search-toggle{display:none}}
@media(max-width:767px){
  .mobile-list{flex:1 1 auto;min-height:0;overflow-x:hidden;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;-webkit-overflow-scrolling:touch}
  .mobile-list .product-card,.mobile-list .product-card.uncounted-product{width:100%;min-width:0;flex:0 0 100%;overflow:visible}
  .metadata-input,.count-inputs input{scroll-margin-block:90px}
  .mobile-navigation button{min-width:112px;min-height:44px}
  .counted-by{align-items:flex-start}.counted-by .counted-at{white-space:normal}
}
</style>
<style scoped>
.all-products-counter{background:#f1f5f9;color:#475569}
.product-status-counters{gap:4px}
.product-status-counter{min-width:32px;height:25px;padding:0 6px;gap:3px;font-size:10px}
.product-status-counter svg{width:12px;height:12px}
</style>
