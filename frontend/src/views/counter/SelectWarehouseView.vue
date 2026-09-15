<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  AlertCircle,
  ArrowRight,
  CalendarDays,
  Check,
  ClipboardCheck,
  KeyRound,
  LockKeyhole,
  LoaderCircle,
  UserRound,
  X,
} from 'lucide-vue-next'
import { getCounterChoices, getCycleCountDetails, getCycleCounts, saveCountingHandoff, verifyCounterAccess } from '../../services/cycleCounts'
import { saveCounterSession } from '../../services/counterSession.js'

const router = useRouter()
const cycleCounts = ref([])
const counters = ref([])
const selectedCycleCountId = ref('')
const selectedCounterId = ref('')
const accessCode = ref('')
const codeInput = ref(null)
const pinEntry = ref(null)
const accessModal = ref(null)
const modalViewportStyle = ref({})
const accessError = ref('')
const verifying = ref(false)
const statusFilter = ref('all')
const modalOpen = ref(false)
const loading = ref(true)
const error = ref('')
const COUNTER_CYCLE_COUNT_TYPE = 'D'
const COUNTER_CYCLE_COUNT_STATUS_ID = 0
const CYCLE_COUNT_REFRESH_INTERVAL_MS = 1500
let refreshTimer = null
let requestPending = false
let disposed = false
let pinScrollFrame = null

// Fit the access modal inside the browser's visible area while the mobile keyboard is open.
function syncModalViewport() {
  // Freeze the keyboard-sized modal while verification is running. Otherwise,
  // closing the keyboard expands visualViewport and visibly drops the sheet.
  if (verifying.value) return
  const viewport = window.visualViewport
  const pinIsFocused = document.activeElement === codeInput.value
  const keyboardIsVisible = Boolean(
    viewport && viewport.height < window.innerHeight - 120,
  )
  if (!modalOpen.value || !viewport || !keyboardIsVisible) {
    modalViewportStyle.value = {}
    return
  }
  modalViewportStyle.value = {
    top: `${viewport.offsetTop}px`,
    height: `${viewport.height}px`,
    bottom: 'auto',
  }

  // Keep only the PIN area visible after the keyboard changes the visual viewport.
  if (pinIsFocused) schedulePinIntoView(false)
}

// Scroll the modal only as far as needed to reveal the PIN input above the keyboard.
function schedulePinIntoView(smooth = true) {
  if (pinScrollFrame) window.cancelAnimationFrame(pinScrollFrame)
  pinScrollFrame = window.requestAnimationFrame(() => {
    pinScrollFrame = null
    const modal = accessModal.value
    const target = pinEntry.value
    if (!modal || !target) return

    const modalRect = modal.getBoundingClientRect()
    const targetRect = target.getBoundingClientRect()
    const footerHeight = modal.querySelector('.modal-actions')?.offsetHeight || 0
    const visibleBottom = modalRect.bottom - footerHeight - 12
    const visibleTop = modalRect.top + 12

    if (targetRect.bottom > visibleBottom) {
      modal.scrollTo({
        top: modal.scrollTop + targetRect.bottom - visibleBottom,
        behavior: smooth ? 'smooth' : 'auto',
      })
    } else if (targetRect.top < visibleTop) {
      modal.scrollTo({
        top: Math.max(0, modal.scrollTop - (visibleTop - targetRect.top)),
        behavior: smooth ? 'smooth' : 'auto',
      })
    }
  })
}

// Filter to type D/status 0 and sort by newest date and ID. Troubleshoot: ccType, statusId, and transDate.
const availableCycleCounts = computed(() =>
  cycleCounts.value
    // Keep records whose normalized type and status match the counter cycle count constants.
    .filter((count) => (
      String(count.ccType || '').toUpperCase() === COUNTER_CYCLE_COUNT_TYPE
      && count.statusId === COUNTER_CYCLE_COUNT_STATUS_ID
    ))
    .sort(
      // Keep work that still needs counting first and review-only records below it.
      (a, b) =>
        Number(isAwaitingPosting(a)) - Number(isAwaitingPosting(b)) ||
        String(b.transDate || '').localeCompare(String(a.transDate || '')) ||
        Number(b.id) - Number(a.id),
    ),
)

// Count unlocked records that still require counting; completed records are review-only.
const unlockedCycleCountCount = computed(() =>
  availableCycleCounts.value.filter(
    (count) => !count.assignedCounterId && progressPercent(count) < 100,
  ).length,
)

// Count completed records that remain visible until the manager posts them.
const awaitingPostingCount = computed(() =>
  availableCycleCounts.value.filter(
    (count) => !count.assignedCounterId && progressPercent(count) === 100,
  ).length,
)

// Filter the visible cards from the compact status controls in the panel heading.
const visibleCycleCounts = computed(() => {
  if (statusFilter.value === 'open') {
    return availableCycleCounts.value.filter((count) => progressPercent(count) < 100)
  }
  if (statusFilter.value === 'review') {
    return availableCycleCounts.value.filter((count) => progressPercent(count) === 100)
  }
  return availableCycleCounts.value
})

function toggleStatusFilter(filter) {
  statusFilter.value = statusFilter.value === filter ? 'all' : filter
}

// Find the selected cycle count by its string ID. Troubleshoot: selectedCycleCountId.
const selectedCount = computed(() =>
  availableCycleCounts.value.find(
    // Find the count whose string ID matches selectedCycleCountId.
    (count) => String(count.id) === selectedCycleCountId.value,
  ),
)

// Resolve the selected Counter for the compact PIN-step identity label.
const selectedCounter = computed(() =>
  counters.value.find((counter) => String(counter.id) === selectedCounterId.value),
)

// Calculate countedRows/totalRows as a percentage capped at 100. Troubleshoot: counts returned by the API.
function progressPercent(count) {
  const total = Number(count.totalRows || 0)
  if (!total) return 0
  return Math.min(100, Math.round((Number(count.countedRows || 0) / total) * 100))
}

// Keep fully counted records reviewable until the manager posts them in the source system.
function isAwaitingPosting(count) {
  return progressPercent(count) === 100
}

// Select a progress color using percentage thresholds. Troubleshoot: progressPercent and threshold values.
function progressColor(count) {
  const percent = progressPercent(count)
  if (percent <= 28) return '#d5222f'
  if (percent <= 58) return '#f15a24'
  if (percent <= 79) return '#d7d900'
  return '#16a34a'
}

// Load cycle counts and manage loading/error state. Troubleshoot: getCycleCounts filters and API response.
async function loadCycleCounts() {
  if (requestPending || disposed) return
  requestPending = true
  loading.value = true
  error.value = ''

  try {
    const [counts, counterChoices] = await Promise.all([
      getCycleCounts(),
      getCounterChoices(),
    ])
    if (disposed) return
    cycleCounts.value = counts
    counters.value = counterChoices
    selectedCycleCountId.value =
      availableCycleCounts.value.length === 1
        ? String(availableCycleCounts.value[0].id)
        : ''
  } catch (requestError) {
    if (!disposed) error.value = requestError.message
  } finally {
    requestPending = false
    if (!disposed) loading.value = false
  }
}

// Open the access modal and select the assigned counter when present. Troubleshoot: count ID and assignedCounterId.
function selectCycleCount(id) {
  selectedCycleCountId.value = String(id)
  // Find the record matching the requested ID, comparing both IDs as strings.
  const count = availableCycleCounts.value.find((item) => String(item.id) === String(id))
  const assignedCounter = counters.value.find(
    // Find the counter matching the selected count's assignedCounterId.
    (counter) => String(counter.id) === String(count?.assignedCounterId),
  )
  selectedCounterId.value = assignedCounter ? String(assignedCounter.id) : ''
  accessCode.value = ''
  accessError.value = ''
  modalOpen.value = true
}

// Close and reset the access modal when verification is idle. Troubleshoot: verifying and modalOpen.
function closeModal() {
  if (verifying.value) return
  modalOpen.value = false
  selectedCycleCountId.value = ''
  selectedCounterId.value = ''
  accessCode.value = ''
  accessError.value = ''
  modalViewportStyle.value = {}
}

// Select a counter unless busy in another count, then focus the PIN input. Troubleshoot: activeCycleCountId and codeInput.
async function selectCounter(id) {
  // Find the record matching the requested ID, comparing both IDs as strings.
  const counter = counters.value.find((item) => String(item.id) === String(id))
  if (
    counter?.activeCycleCountId &&
    String(counter.activeCycleCountId) !== selectedCycleCountId.value
  ) return
  selectedCounterId.value = String(id)
  accessCode.value = ''
  accessError.value = ''
  await nextTick()
  codeInput.value?.focus({ preventScroll: true })
  syncModalViewport()
  schedulePinIntoView(true)
}

// Return to the full Counter list without closing the Cycle Count access dialog.
function changeCounter() {
  selectedCounterId.value = ''
  accessCode.value = ''
  accessError.value = ''
  accessModal.value?.scrollTo({ top: 0, behavior: 'smooth' })
}

// Validate the four-digit code, obtain a session, and open the count. Troubleshoot: accessError, lock conflicts, and the stored token.
async function openCycleCount() {
  // Retain the chosen count while background refreshes update the available cards.
  const count = selectedCount.value
  if (!count || verifying.value || disposed) return
  if (!selectedCounterId.value) {
    accessError.value = 'Select your Counter name first.'
    return
  }
  if (!/^\d{4}$/.test(accessCode.value)) {
    accessError.value = 'Enter your 4-digit Counter access code.'
    return
  }

  verifying.value = true
  accessError.value = ''
  try {
    const session = await verifyCounterAccess(
      count.id,
      selectedCounterId.value,
      accessCode.value,
    )
    if (disposed) return
    saveCounterSession(count.id, session)
    // Start the authorized product request once, then let the destination page
    // await the same promise instead of holding the PIN screen open.
    const detailsPromise = getCycleCountDetails(count.id, session.token)
    saveCountingHandoff(count.id, session.token, count, detailsPromise)
    accessCode.value = ''
    await router.push({
      path: `/counter/count/${count.id}`,
      query: { code: count.code || count.id },
    })
  } catch (requestError) {
    accessError.value = requestError.message
  } finally {
    verifying.value = false
  }
  if (accessError.value && !disposed) {
    await nextTick()
    codeInput.value?.focus({ preventScroll: true })
  }
}

// Refresh count cards and counter lock states together so expired locks disappear without a page reload.
async function refreshCycleCounts() {
  // Do not replace modal data or compete with PIN verification while the access dialog is active.
  if (requestPending || disposed || modalOpen.value || verifying.value) return
  requestPending = true
  try {
    const [counts, counterChoices] = await Promise.all([
      getCycleCounts(),
      getCounterChoices(),
    ])
    if (!disposed) {
      cycleCounts.value = counts
      counters.value = counterChoices
    }
  } catch {
    // Keep the current cards; the next refresh can recover.
  } finally {
    requestPending = false
  }
}

// Refresh when the tab becomes visible. Troubleshoot: visibilitychange listener and visibilityState.
function refreshWhenVisible() {
  if (document.visibilityState === 'visible') refreshCycleCounts()
}

// On mount, reset scrolling, load cards, and start the refresh timer and listeners.
onMounted(async () => {
  window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  document.documentElement.scrollTop = 0
  document.body.scrollTop = 0
  document.body.classList.add('cycle-count-selection-active')
  await loadCycleCounts()
  // An unfinished initial request must not install timers after the page has been left.
  if (disposed) return
  refreshTimer = window.setInterval(refreshCycleCounts, CYCLE_COUNT_REFRESH_INTERVAL_MS)
  document.addEventListener('visibilitychange', refreshWhenVisible)
  window.addEventListener('focus', refreshCycleCounts)
  window.visualViewport?.addEventListener('resize', syncModalViewport)
  window.visualViewport?.addEventListener('scroll', syncModalViewport)
})

// On unmount, clear the selection CSS class, refresh timer, and focus/visibility listeners.
onUnmounted(() => {
  disposed = true
  document.body.classList.remove('cycle-count-selection-active')
  if (refreshTimer) window.clearInterval(refreshTimer)
  document.removeEventListener('visibilitychange', refreshWhenVisible)
  window.removeEventListener('focus', refreshCycleCounts)
  window.visualViewport?.removeEventListener('resize', syncModalViewport)
  window.visualViewport?.removeEventListener('scroll', syncModalViewport)
  if (pinScrollFrame) window.cancelAnimationFrame(pinScrollFrame)
})
</script>

<template>
  <main class="selection-page">
    <section class="welcome">
      <h1>Select Cycle Count</h1>
      <p>Select an available Cycle Count to begin the counting process.</p>
    </section>

    <section v-if="loading" class="selection-panel card state-card">
      <LoaderCircle class="spin" :size="28" />
      <strong>Loading Cycle Counts...</strong>
    </section>

    <section v-else-if="error" class="selection-panel card state-card error-state">
      <AlertCircle :size="28" />
      <strong>Could not load Cycle Counts</strong>
      <span>{{ error }}</span>
      <button class="btn btn-secondary" type="button" @click="loadCycleCounts">Try again</button>
    </section>

    <section v-else class="selection-panel card" aria-labelledby="cycle-count-heading">
      <div class="panel-heading">
        <div class="heading-icon"><ClipboardCheck :size="27" /></div>
        <div class="heading-copy">
          <h2 id="cycle-count-heading">Cycle Counts</h2>
          <p>Continue counting or review records awaiting manager posting.</p>
        </div>
        <span class="status-counters" aria-label="Filter Cycle Counts by status">
          <button type="button" :class="['status-counter', 'all-count', { active: statusFilter === 'all' }]" :aria-pressed="statusFilter === 'all'" :aria-label="`Show all ${availableCycleCounts.length} Cycle Counts`" title="Show all Cycle Counts" @click="statusFilter = 'all'">All {{ availableCycleCounts.length }}</button>
          <button type="button" :class="['status-counter', 'open-count', { empty: unlockedCycleCountCount === 0, active: statusFilter === 'open' }]" :aria-pressed="statusFilter === 'open'" :aria-label="`Show ${unlockedCycleCountCount} open Cycle Counts`" title="Show open Cycle Counts" @click="toggleStatusFilter('open')"><Check :size="14" />{{ unlockedCycleCountCount }}</button>
          <button v-if="awaitingPostingCount" type="button" :class="['status-counter', 'review-count', { active: statusFilter === 'review' }]" :aria-pressed="statusFilter === 'review'" :aria-label="`Show ${awaitingPostingCount} Cycle Counts open for review`" title="Show Cycle Counts open for review" @click="toggleStatusFilter('review')"><ClipboardCheck :size="14" />{{ awaitingPostingCount }}</button>
        </span>
      </div>

      <div v-if="visibleCycleCounts.length" class="count-grid">
        <button
          v-for="count in visibleCycleCounts"
          :key="count.id"
          type="button"
          :class="['count-option', { selected: selectedCycleCountId === String(count.id), locked: count.assignedCounterId, 'awaiting-posting': isAwaitingPosting(count) }]"
          :disabled="Boolean(count.assignedCounterId)"
          :aria-pressed="selectedCycleCountId === String(count.id)"
          :aria-label="count.assignedCounterId ? `${count.code || `Cycle Count ${count.id}`} is active with Counter ${count.assignedCounterNumber || count.assignedCounterId}` : isAwaitingPosting(count) ? `Open ${count.code || `Cycle Count ${count.id}`} for recount` : `Open ${count.code || `Cycle Count ${count.id}`}`"
          @click="selectCycleCount(count.id)"
        >
          <span class="count-label">Cycle Count</span>
          <strong>{{ count.code || `Cycle Count ${count.id}` }}</strong>
          <span v-if="count.assignedCounterId" class="assignment-lock">
            <LockKeyhole :size="14" />
            <span>Active: <strong>Counter {{ count.assignedCounterNumber || count.assignedCounterId }}</strong></span>
          </span>
          <span v-else-if="isAwaitingPosting(count)" class="assignment-available posting-status"><ClipboardCheck :size="14" />Counted · Open for Recount</span>
          <span v-else class="assignment-available"><Check :size="14" />Available</span>
          <span class="count-meta"><span class="count-date"><CalendarDays :size="15" />{{ count.transDate || 'No transaction date' }}</span><span class="record-id">ID {{ count.id }}</span></span>
          <span class="count-progress">
            <span class="progress-copy">
              <strong>{{ count.countedRows || 0 }}/{{ count.totalRows || 0 }}</strong>
              <span class="progress-ring" :aria-label="`${progressPercent(count)}% complete`">
                <svg viewBox="0 0 36 36" aria-hidden="true">
                  <circle class="progress-ring-track" cx="18" cy="18" r="15.5" />
                  <circle class="progress-ring-value" cx="18" cy="18" r="15.5" pathLength="100" :stroke-dasharray="`${progressPercent(count)} 100`" :style="{ stroke: progressColor(count) }" />
                </svg>
                <span>{{ progressPercent(count) }}%</span>
              </span>
            </span>
            <span class="progress-track" aria-hidden="true"><span :style="{ width: `${progressPercent(count)}%`, backgroundColor: progressColor(count) }"></span></span>
          </span>
          <span class="open-indicator">
            <LockKeyhole v-if="count.assignedCounterId" :size="17" />
            <ArrowRight v-else :size="18" />
          </span>
        </button>
      </div>

      <div v-else class="empty-state">
        <ClipboardCheck :size="24" />
        <span>{{ availableCycleCounts.length ? 'No Cycle Counts match this filter.' : 'No Cycle Count with CC Type D and status ID 0 is currently available.' }}</span>
      </div>

    </section>

   <div class="security-note">
  © 2026 S&P Enterprises Inc. · IT Dept.
</div>

    <Teleport to="body">
      <Transition name="modal-fade">
      <div v-if="modalOpen && selectedCount" class="modal-backdrop" :style="modalViewportStyle" @click.self="closeModal">
        <section ref="accessModal" :class="['access-modal', { 'pin-step': selectedCounterId, verifying }]" role="dialog" aria-modal="true" aria-labelledby="access-title" :aria-busy="verifying" @keydown.esc="closeModal">
          <header class="modal-header">
            <div><span>Open Cycle Count</span><h2 id="access-title">{{ selectedCount.code || selectedCount.id }}</h2></div>
            <button type="button" aria-label="Close" :disabled="verifying" @click="closeModal"><X :size="22" /></button>
          </header>

          <div class="modal-body">
            <p v-if="selectedCount.assignedCounterId" class="locked-message">
              <LockKeyhole :size="18" />
              <span>This Cycle Count is locked to <strong>Counter {{ selectedCount.assignedCounterNumber || selectedCount.assignedCounterId }}</strong>. Only this counter can continue.</span>
            </p>
            <fieldset :class="['counter-step', { 'has-selection': selectedCounterId }]">
              <legend>1. Select your Counter</legend>
              <div v-if="counters.length" class="counter-choices">
                <button
                  v-for="counter in counters"
                  :key="counter.id"
                  type="button"
                  :class="{ selected: selectedCounterId === String(counter.id) }"
                  :tabindex="selectedCounterId && selectedCounterId !== String(counter.id) ? -1 : 0"
                  :disabled="(selectedCount.assignedCounterId && String(counter.id) !== String(selectedCount.assignedCounterId)) || (counter.activeCycleCountId && String(counter.activeCycleCountId) !== String(selectedCount.id))"
                  @click="selectCounter(counter.id)"
                >
                  <UserRound :size="18" />
                  <span><strong>Counter {{ counter.counterNumber }}</strong><small v-if="counter.activeCycleCountId">Active in Cycle Count ID {{ counter.activeCycleCountId }}</small><small v-else>{{ counter.name }}</small></span>
                  <Check v-if="selectedCounterId === String(counter.id)" :size="18" />
                </button>
              </div>
              <p v-else class="no-counters">No active Counter account. Ask the administrator to create one.</p>
            </fieldset>

            <form v-if="selectedCounterId" ref="pinEntry" class="access-form code-reveal" @submit.prevent="openCycleCount">
              <div class="pin-counter">
                <span><UserRound :size="17" /><strong>Counter {{ selectedCounter?.counterNumber }}</strong><small v-if="selectedCounter?.name">· {{ selectedCounter.name }}</small></span>
                <button class="change-counter" type="button" :disabled="verifying" @click="changeCounter">Change Counter</button>
              </div>
              <label class="pin-label" for="counter-code">Enter your 4-digit PIN</label>
              <div class="code-field">
                <KeyRound :size="20" />
                <input
                  id="counter-code"
                  ref="codeInput"
                  v-model="accessCode"
                  type="password"
                  inputmode="numeric"
                  pattern="[0-9]*"
                  maxlength="4"
                  autocomplete="one-time-code"
                  placeholder="••••"
                  :disabled="verifying"
                  @focus="syncModalViewport"
                  @blur="syncModalViewport"
                  @input="accessCode = accessCode.replace(/\D/g, '').slice(0, 4); accessError = ''"
                />
              </div>
              <p v-if="accessError" class="access-error" role="alert">{{ accessError }}</p>
            </form>
          </div>

          <footer v-if="selectedCounterId" class="modal-actions single-action">
            <button class="btn btn-primary" type="button" :disabled="verifying" @click="openCycleCount">
              <LoaderCircle v-if="verifying" class="spin" :size="19" />
              {{ verifying ? 'Verifying...' : 'Verify' }}
              <ArrowRight v-if="!verifying" :size="19" />
            </button>
          </footer>
        </section>
      </div>
      </Transition>
    </Teleport>
  </main>
</template>
 
 <style scoped>
.selection-page{width:min(920px,100%);margin:0 auto;padding:34px 24px 48px}.welcome{text-align:center;margin:8px auto 26px;max-width:650px}.welcome h1{font-size:clamp(28px,5vw,38px);line-height:1.1;margin:8px 0;color:#15351e}.welcome p{margin:0;color:#64748b;line-height:1.55}.selection-panel{padding:24px}.panel-heading{display:flex;align-items:center;gap:13px;margin-bottom:20px}.heading-icon{width:50px;height:50px;flex:0 0 50px;border-radius:15px;background:#eaf7ed;color:#166534;display:grid;place-items:center}.panel-heading h2{margin:0;font-size:22px}.panel-heading p{margin:3px 0 0;color:#64748b;font-size:14px}.count-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.count-option{position:relative;min-height:112px;padding:15px 48px 14px 16px;text-align:left;border:2px solid #dce5de;background:#fff;border-radius:14px;color:#17211b}.count-option:hover{background:#f8fbf8;border-color:#acd3b5}.count-option.selected{border-color:#15803d;background:#f0fdf4;box-shadow:0 0 0 3px rgba(21,128,61,.09)}.count-label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#64748b;font-weight:800}.count-option strong{display:block;margin-top:3px;font-size:19px;color:#14532d;overflow-wrap:anywhere}.count-date{display:flex;align-items:center;gap:5px;margin-top:10px;color:#475569;font-size:12px;font-weight:700}.record-id{display:block;margin-top:5px;color:#64748b;font-size:11px}.access-form{margin:0 0 12px;padding:14px;border:1px solid #dce5de;border-radius:12px;background:#f8faf8}.access-form>label{display:block;margin-bottom:7px;color:#334155;font-size:13px;font-weight:900}.code-field{position:relative}.code-field svg{position:absolute;left:14px;top:50%;transform:translateY(-50%);color:#166534}.code-field input{width:100%;min-height:52px;padding:8px 14px 8px 46px;border:2px solid #86c995;border-radius:10px;background:#fff;color:#14532d;font-size:22px;font-weight:900;letter-spacing:.3em}.code-field input:focus{outline:3px solid rgba(21,128,61,.13);border-color:#15803d}.access-form>p{margin:6px 0 0;color:#64748b;font-size:11px}.access-form .access-error{color:#b91c1c;font-size:12px;font-weight:800}.empty-state{min-height:130px;padding:20px;border:1px dashed #cbd5ce;border-radius:12px;color:#64748b;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;text-align:center}.security-note{display:flex;justify-content:center;align-items:center;gap:8px;color:#64748b;font-size:13px;font-weight:700;margin-top:18px}.state-card{min-height:240px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;text-align:center;color:#64748b}.state-card strong{color:#334155}.error-state svg{color:#b91c1c}
@media(max-width:600px){.selection-page{padding:18px 10px 30px}.welcome{margin-bottom:14px}.welcome h1{font-size:26px;margin:5px 0}.welcome p{font-size:13px;line-height:1.4}.selection-panel{padding:12px}.panel-heading{align-items:center;gap:10px;margin-bottom:12px}.heading-icon{width:40px;height:40px;flex-basis:40px;border-radius:11px}.panel-heading h2{font-size:17px}.panel-heading p{font-size:12px}.count-grid{grid-template-columns:1fr;gap:7px}.count-option{min-height:70px;padding:10px 40px 9px 12px;border-width:1px;border-radius:10px}.count-label{font-size:9px}.count-option strong{margin-top:1px;font-size:16px}.count-date{display:inline-flex;margin-top:5px;font-size:11px}.record-id{display:inline;margin-left:9px;font-size:10px}.security-note{text-align:center;padding:0 8px;margin-top:13px;font-size:12px}}
.modal-backdrop{position:fixed;inset:0;z-index:100;background:rgba(15,23,42,.58);display:flex;align-items:center;justify-content:center;padding:16px}.access-modal{width:min(520px,100%);max-height:calc(100dvh - 32px);overflow:auto;border-radius:18px;background:#fff;box-shadow:0 24px 70px rgba(15,23,42,.28)}.modal-header{position:sticky;top:0;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:17px 18px;border-bottom:1px solid #e5ebe6;background:#fff}.modal-header span{font-size:11px;text-transform:uppercase;color:#64748b;font-weight:900}.modal-header h2{margin:3px 0 0;color:#14532d;font-size:21px}.modal-header button{width:44px;height:44px;flex:0 0 44px;border:0;border-radius:10px;background:#f1f5f2;color:#475569;display:grid;place-items:center}.modal-body{display:grid;gap:16px;padding:18px}.modal-body fieldset{position:relative;margin:0;padding:0;border:0}.modal-body legend,.modal-body .access-form>label{margin-bottom:9px;color:#334155;font-size:13px;font-weight:900}.pin-counter{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:13px}.pin-counter>span{min-width:0;display:flex;align-items:center;gap:5px;color:#166534}.pin-counter strong{font-size:13px;white-space:nowrap}.pin-counter small{min-width:0;overflow:hidden;color:#64748b;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.pin-label{display:block}.change-counter{flex:0 0 auto;padding:5px 8px;border:0;border-radius:7px;background:#edf7ef;color:#166534;font-size:11px;font-weight:900}.counter-choices{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.counter-choices button{min-height:54px;padding:9px 11px;border:1px solid #dce5de;border-radius:10px;background:#fff;color:#334155;display:flex;align-items:center;gap:7px;text-align:left;font-size:13px;font-weight:800}.counter-choices button span{min-width:0;flex:1;overflow-wrap:anywhere}.counter-choices button strong,.counter-choices button small{display:block}.counter-choices button small{margin-top:2px;color:#64748b;font-size:11px;font-weight:700}.counter-choices button.selected{border-color:#15803d;background:#f0fdf4;color:#166534;box-shadow:0 0 0 2px rgba(21,128,61,.09)}.no-counters{margin:0;padding:13px;border-radius:10px;background:#fff7ed;color:#9a3412;font-size:12px}.modal-body .access-form{margin:0;padding:0;border:0;background:transparent}.code-reveal{animation:reveal-code .16s ease-out}.code-field input:disabled{background:#f1f5f2;color:#94a3b8}.modal-actions{position:sticky;bottom:0;display:grid;grid-template-columns:.7fr 1.3fr;gap:9px;padding:13px 18px;border-top:1px solid #e5ebe6;background:#fff}.modal-actions.single-action{grid-template-columns:1fr}.modal-actions .btn{min-height:48px}.modal-actions .btn-primary{display:flex;align-items:center;justify-content:center;gap:6px}@keyframes reveal-code{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}
.modal-fade-enter-active,.modal-fade-leave-active{transition:opacity .16s ease}.modal-fade-enter-active .access-modal,.modal-fade-leave-active .access-modal{transition:transform .18s ease,opacity .16s ease}.modal-fade-enter-from,.modal-fade-leave-to{opacity:0}.modal-fade-enter-from .access-modal,.modal-fade-leave-to .access-modal{opacity:0;transform:translateY(10px) scale(.985)}
@media(prefers-reduced-motion:reduce){.code-reveal{animation:none}}
@media(max-width:600px){.modal-backdrop{align-items:flex-end;padding:0}.access-modal{width:100%;height:min(72svh,560px);max-height:100%;display:flex;flex-direction:column;overflow:hidden;border-radius:18px 18px 0 0;transition:height .16s ease}.access-modal.pin-step{height:min(310px,100%)}.access-modal.verifying{transition:none}.modal-header{position:relative;flex:0 0 auto;padding:14px}.modal-body{flex:1 1 auto;min-height:0;padding:14px;overflow-y:auto;overscroll-behavior:contain}.pin-step .modal-body{display:flex;align-items:center}.counter-choices{grid-template-columns:1fr;gap:7px}.counter-choices button{min-height:48px}.counter-step.has-selection{display:none}.modal-actions{position:relative;flex:0 0 auto;padding:10px 14px calc(10px + env(safe-area-inset-bottom))}.code-field input{font-size:24px}}

/* Compact, touch-first Cycle Count cards. */
.panel-heading .heading-copy{min-width:0;flex:1}.status-counters{display:flex;flex:0 0 auto;align-items:center;gap:6px}.status-counter{min-width:38px;height:30px;padding:0 8px;border:1px solid transparent;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;gap:5px;font-size:12px;font-weight:900;cursor:pointer}.status-counter.active{border-color:#15803d;box-shadow:0 0 0 3px rgba(21,128,61,.14)}.open-count{background:#edf7ef;color:#166534}.open-count.empty{background:#e5e7eb;color:#64748b}.review-count{background:#dcfce7;color:#14532d}.count-option{overflow:hidden;transition:border-color .18s ease,background .18s ease,transform .18s ease,box-shadow .18s ease}.count-option::before{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:#22a447}.count-meta{display:flex;align-items:center;gap:8px;margin-top:10px}.count-meta .count-date{display:inline-flex;margin:0;padding:5px 8px;border-radius:7px;background:#f1f7f2;color:#475569}.count-meta .record-id{display:inline;margin:0;color:#94a3b8}.open-indicator{position:absolute;right:14px;top:50%;width:32px;height:32px;transform:translateY(-50%);border-radius:9px;background:#edf7ef;color:#166534;display:grid;place-items:center;transition:background .18s ease,color .18s ease,transform .18s ease}.count-option:active .open-indicator{transform:translateY(-50%) scale(.92)}
.count-progress{display:block;margin-top:10px}.progress-copy{display:flex;align-items:center;justify-content:space-between;color:#64748b;font-size:11px}.progress-copy strong{display:inline;margin:0;color:#166534;font-size:12px}.progress-track{display:block;height:7px;margin-top:5px;overflow:hidden;border-radius:999px;background:#e2e8f0}.progress-track>span{display:block;height:100%;border-radius:inherit;background:#22a447;transition:width .25s ease}
.assignment-lock{display:flex;align-items:center;gap:5px;width:fit-content;max-width:100%;margin-top:7px;padding:4px 7px;border:1px solid #fbbf24;border-radius:6px;background:#fffbeb;color:#92400e;font-size:11px;font-weight:700}.assignment-lock>svg{flex:0 0 auto}.assignment-lock span{min-width:0;overflow-wrap:anywhere}.assignment-lock strong{display:inline;margin:0;color:#78350f;font-size:11px}.locked-message{display:flex;align-items:flex-start;gap:8px;margin:0;padding:11px 12px;border:1px solid #fbbf24;border-radius:10px;background:#fffbeb;color:#92400e;font-size:12px;line-height:1.45}.locked-message svg{flex:0 0 auto;margin-top:1px}.counter-choices button:disabled{opacity:.42;cursor:not-allowed;background:#f1f5f2}
.assignment-available{display:flex;align-items:center;gap:4px;width:fit-content;margin-top:7px;padding:4px 7px;border:1px solid #86c995;border-radius:6px;background:#f0fdf4;color:#166534;font-size:11px;font-weight:800}
.count-option.awaiting-posting{border-color:#86c995;background:#f7fff9}.count-option.awaiting-posting::before{background:#15803d}.posting-status{border-color:#4ade80;background:#dcfce7;color:#14532d}
.count-option.locked{cursor:not-allowed;border-color:#f3d38b;background:#fffdf5;color:#64748b}.count-option.locked::before{background:#f59e0b}.count-option.locked .open-indicator{background:#fef3c7;color:#92400e}
@media(hover:hover){.count-option:not(:disabled):hover{transform:translateY(-2px);box-shadow:0 9px 22px rgba(15,23,42,.08)}.count-option:not(:disabled):hover .open-indicator{background:#15803d;color:#fff}}
@media(max-width:600px){.panel-heading p{display:none}.status-counters{gap:4px}.status-counter{min-width:34px;height:28px;padding:0 7px;font-size:11px}.count-meta{gap:6px;margin-top:5px}.count-meta .count-date{margin:0;padding:3px 6px;font-size:10px}.count-meta .record-id{margin:0;font-size:9px}.count-progress{margin-top:7px}.progress-track{height:5px}.open-indicator{right:9px;width:28px;height:28px;border-radius:8px}}
@media(prefers-reduced-motion:reduce){.count-option,.open-indicator,.modal-fade-enter-active,.modal-fade-leave-active,.modal-fade-enter-active .access-modal,.modal-fade-leave-active .access-modal{transition:none}.count-option:hover{transform:none}.code-reveal{animation:none}}

/* Final responsive Select Cycle Count layout. */
.security-note{position:fixed;right:0;bottom:0;left:0;z-index:10;margin:0;padding:14px 24px;pointer-events:none;background:#f4f7f4}
.progress-copy>.progress-ring{position:relative;display:grid;width:40px;height:40px;flex:0 0 40px;place-items:center;padding:0;border-radius:50%;background:transparent;color:#17211b;font-size:9px;font-weight:900;line-height:1;box-shadow:none}.progress-ring svg{position:absolute;inset:0;width:100%;height:100%;transform:rotate(-90deg)}.progress-ring circle{fill:none;stroke-width:4}.progress-ring-track{stroke:#e2e8f0}.progress-ring-value{stroke-linecap:round;transition:stroke-dasharray .2s ease}.progress-ring>span{position:relative;z-index:1}
:global(body.cycle-count-selection-active){overflow:hidden}
@media(min-width:601px){.selection-page{width:min(960px,100%);height:auto;min-height:0;flex:1;padding:24px 20px 20px;display:flex;flex-direction:column;overflow:hidden}.welcome{flex:0 0 auto;margin-bottom:18px}.selection-page>.selection-panel{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;overflow:hidden}.panel-heading{flex:0 0 auto}.count-grid{flex:1 1 auto;min-height:0;align-content:start;grid-auto-rows:max-content;padding-right:6px;overflow-x:hidden;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#cbd5ce transparent}.count-grid::-webkit-scrollbar{width:6px}.count-grid::-webkit-scrollbar-track{background:transparent}.count-grid::-webkit-scrollbar-thumb{border-radius:999px;background:#cbd5ce}.security-note{position:static;flex:0 0 auto;margin:12px 0 0;padding:0;background:transparent}}
@media(min-width:1024px){.selection-page{width:min(1080px,100%);padding:24px 24px 18px}.welcome{margin-bottom:18px}.selection-panel{padding:18px 20px}.count-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.count-option{min-height:100px;padding:12px 48px 12px 14px}.count-meta,.count-progress{margin-top:8px}}
@media(max-width:600px){.selection-page{height:calc(100vh - 63px);height:calc(100svh - 63px);min-height:0;padding-bottom:calc(40px + env(safe-area-inset-bottom));overflow:hidden;overscroll-behavior:none}.selection-page>.selection-panel{height:clamp(280px,calc(100vh - 230px),600px);height:clamp(280px,calc(100svh - 230px),600px);min-height:280px;flex:1 1 auto;display:flex;flex-direction:column;overflow:hidden}.count-grid{flex:1 1 0;min-height:180px;align-content:start;grid-auto-rows:max-content;padding:0 2px 3px 0;overflow-x:hidden;overflow-y:scroll;overscroll-behavior:contain;touch-action:pan-y;-webkit-overflow-scrolling:touch}.counter-choices{max-height:42vh;max-height:42svh;padding-right:2px;overflow-x:hidden;overflow-y:auto;overscroll-behavior:contain;touch-action:pan-y;-webkit-overflow-scrolling:touch}.security-note{padding:11px 12px calc(11px + env(safe-area-inset-bottom));font-size:11px}.count-option{min-height:136px;padding:12px 58px 13px 14px}.count-option strong{font-size:16px;line-height:1.2}.count-option .assignment-available,.count-option .assignment-lock{margin-top:6px}.count-option .count-meta{margin-top:6px}.count-option .count-progress{margin-top:8px;padding-right:38px}.count-option .progress-copy{justify-content:flex-start}.count-option .progress-ring{position:absolute;right:11px;bottom:11px;width:38px;height:38px;flex-basis:38px;font-size:8px}.count-option .open-indicator{top:11px;right:11px;transform:none}.count-option:active .open-indicator{transform:scale(.92)}}
</style>
<style scoped>
.all-count{background:#f1f5f9;color:#475569}
.status-counters{gap:4px}
.status-counter{min-width:32px;height:26px;padding:0 6px;gap:3px;font-size:10px}
.status-counter svg{width:12px;height:12px}
</style>
