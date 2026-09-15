import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'
import { computed, effectScope, nextTick, ref, watch } from 'vue'

const root = fileURLToPath(new URL('../../', import.meta.url))

// Hold a request open so tests can exercise overlapping requests and navigation during loading.
function deferred() {
  let resolve, reject
  const promise = new Promise((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

// Run the real source in an isolated browser-like environment without network or database access.
async function harness(api = {}) {
  const storage = new Map()
  const intervals = new Map()
  const timeouts = new Map()
  const listeners = new Map()
  const mounted = [], unmounted = []
  const scope = effectScope()
  const navigations = []
  const emitted = []
  let nextTimer = 1
  const apiCalls = []
  const router = {
    push: async (target) => { navigations.push(target) },
    replace: async (target) => { navigations.push(target) },
    resolve: value => api.resolve?.(value) ?? { fullPath: value, params: {}, meta: {} },
  }
  const sessionStorage = {
    get length() { return storage.size },
    key: index => [...storage.keys()][index] ?? null,
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: key => storage.delete(key),
  }
  const events = {
    addEventListener: (event, callback) => listeners.set(event, callback),
    removeEventListener: event => listeners.delete(event),
  }
  const navigator = {
    onLine: api.online ?? true,
    sendBeacon: (...args) => api.beacon?.(...args) ?? false,
  }
  const context = vm.createContext({
    sessionStorage, Blob, URLSearchParams, AbortController, CustomEvent,
    defineProps: () => api.props || {},
    defineEmits: () => (...args) => emitted.push(args),
    fetch: (...args) => api.fetch(...args),
    navigator,
    window: {
      ...events, scrollTo() {},
      dispatchEvent: event => listeners.get(event.type)?.(event),
      setTimeout: (callback, delay) => { const id = nextTimer++; timeouts.set(id, { callback, delay }); return id },
      clearTimeout: id => timeouts.delete(id),
      setInterval: (callback, delay) => { const id = nextTimer++; intervals.set(id, { callback, delay }); return id },
      clearInterval: id => intervals.delete(id),
    },
    document: {
      ...events, visibilityState: 'visible', documentElement: { scrollTop: 0 },
      body: { scrollTop: 0, classList: { add() {}, remove() {} } },
    },
  })
  const mocks = {
    vue: { computed, ref, watch, nextTick,
      onMounted: callback => mounted.push(callback),
      onUnmounted: callback => unmounted.push(callback),
      onBeforeUnmount: callback => unmounted.push(callback),
    },
    'vue-router': { useRouter: () => router, useRoute: () => api.route || { query: {}, params: {}, meta: {} } },
    [path.join(root, 'src/stores/auth.js')]: { useAuthStore: () => ({ isLoggedIn: false }) },
    'lucide-vue-next': Object.fromEntries(['AlertCircle', 'ArrowRight', 'CalendarDays', 'Check', 'ClipboardCheck', 'KeyRound', 'LockKeyhole', 'LoaderCircle', 'UserRound', 'X'].map(name => [name, {}])),
    [path.join(root, 'src/services/api.js')]: {
      apiUrl: value => `/api${value}`,
      apiGet: async (...args) => { apiCalls.push(['get', ...args]); return api.get?.(...args) ?? [] },
      apiPost: async (...args) => { apiCalls.push(['post', ...args]); return api.post?.(...args) ?? {} },
      apiPatch: async (...args) => { apiCalls.push(['patch', ...args]); return api.patch?.(...args) ?? {} },
      apiDelete: async (...args) => { apiCalls.push(['delete', ...args]); return api.delete?.(...args) ?? {} },
      fetchAllPages: async (...args) => { apiCalls.push(['list', ...args]); return api.list?.(...args) ?? [] },
    },
  }
  if (api.realTransport) delete mocks[path.join(root, 'src/services/api.js')]
  const modules = new Map()

  // Resolve application imports and expose only selection-page state needed for behavior assertions.
  async function load(id) {
    if (modules.has(id)) return modules.get(id)
    let module
    if (mocks[id]) {
      const exports = mocks[id]
      module = new vm.SyntheticModule(Object.keys(exports), function () {
        for (const [name, value] of Object.entries(exports)) this.setExport(name, value)
      }, { context, identifier: id })
    } else {
      let source = await readFile(id, 'utf8')
      if (id.endsWith('.vue')) {
        source = source.match(/<script setup>([\s\S]*?)<\/script>/)[1]
        source += '\nexport { loadCycleCounts, refreshCycleCounts, openCycleCount, cycleCounts, selectedCycleCountId, selectedCounterId, accessCode, verifying, loading, error };'
      }
      module = new vm.SourceTextModule(source, { context, identifier: id, initializeImportMeta: meta => { meta.env = {} } })
    }
    modules.set(id, module)
    await module.link(async (specifier, parent) => {
      if (!specifier.startsWith('.')) return load(specifier)
      let resolved = path.resolve(path.dirname(parent.identifier), specifier)
      if (!path.extname(resolved)) resolved += '.js'
      return load(resolved)
    })
    return module
  }

  // Evaluate the requested module, including its real service dependencies.
  async function open(relativePath) {
    const module = await load(path.join(root, relativePath))
    await module.evaluate()
    return module.namespace
  }

  // Trigger lifecycle cleanup and stop reactive effects, matching removal of the owning component.
  function unmount() {
    unmounted.forEach(callback => callback())
    scope.stop()
  }

  return { open, storage, intervals, timeouts, listeners, mounted, unmount, navigations, apiCalls, scope, emitted, navigator }
}

// Verify compatibility with existing sessions and isolation from staff and other counter sessions.
test('session storage preserves existing keys and handles malformed JSON', async () => {
  const h = await harness()
  const session = await h.open('src/services/counterSession.js')
  h.storage.set('wms-counter-session-7', '{bad json')
  assert.equal(session.readCounterSession(7), null)
  assert.equal(session.readCounterSession(8), null)
  h.storage.set('wms-staff-token', 'staff-token')
  session.saveCounterSession(7, { token: 'counter-token', counter: { id: 2 } })
  session.saveCounterSession(8, { token: 'other-token' })
  assert.equal(session.readCounterSession('7').counter.id, 2)
  session.clearCounterSession(7)
  assert.equal(h.storage.get('wms-staff-token'), 'staff-token')
  assert.equal(session.readCounterSession(8).token, 'other-token')
})

// Confirm that failed unlocks retain access and successful unlocks use the unchanged API contract.
test('unlock retains the token on failure and clears it only after success', async () => {
  let fail = true
  const h = await harness({ post: async () => { if (fail) throw Error('offline') } })
  const session = await h.open('src/services/counterSession.js')
  session.saveCounterSession(7, { token: 'token' })
  await assert.rejects(session.releaseCounterSession(7), /offline/)
  assert.equal(session.readCounterSession(7).token, 'token')
  fail = false
  await session.releaseCounterSession(7)
  assert.equal(session.readCounterSession(7), null)
  assert.equal(h.apiCalls[0][1], '/cycle-counts/7/unlock/')
  assert.equal(h.apiCalls[0][3].headers['X-Counter-Session'], 'token')
})

// A late unlock response must not erase a replacement session created while the request was pending.
test('unlock does not clear a newer session', async () => {
  const request = deferred()
  const h = await harness({ post: () => request.promise })
  const session = await h.open('src/services/counterSession.js')
  session.saveCounterSession(7, { token: 'old' })
  const pending = session.releaseCounterSession(7)
  session.saveCounterSession(7, { token: 'new' })
  request.resolve({})
  await pending
  assert.equal(session.readCounterSession(7).token, 'new')
})

// Beacon failure preserves the token; successful queueing uses the existing JSON body and endpoint.
test('beacon fallback preserves its existing queue semantics', async () => {
  let queued = false, beaconArgs
  const h = await harness({ beacon: (...args) => { beaconArgs = args; return queued } })
  const session = await h.open('src/services/counterSession.js')
  session.saveCounterSession(7, { token: 'token' })
  assert.equal(session.releaseCounterSessionOnExit(7), false)
  assert.equal(session.readCounterSession(7).token, 'token')
  queued = true
  assert.equal(session.releaseCounterSessionOnExit(7), true)
  assert.equal(session.readCounterSession(7), null)
  assert.equal(beaconArgs[0], '/api/cycle-counts/7/unlock/')
  assert.deepEqual(JSON.parse(await beaconArgs[1].text()), { counterSession: 'token' })
})

// Desktop and mobile share this service, which sends only new metadata values and never *_from history.
test('actual-count update sends editable metadata through the shared API contract', async () => {
  const h = await harness()
  const service = await h.open('src/services/cycleCounts.js')
  await service.updateActualCount(9, 2, 3, 'counter-token', 7, {
    productionDate: '2026-01-02',
    expiryDate: null,
    lotNo: 'LOT002',
  })
  const call = h.apiCalls[0]
  assert.equal(call[0], 'patch')
  assert.equal(call[1], '/cycle-count-details/9/actual-count/')
  assert.deepEqual(JSON.parse(JSON.stringify(call[2])), {
    actualCs: 2,
    actualPc: 3,
    productionDate: '2026-01-02',
    expiryDate: null,
    lotNo: 'LOT002',
  })
  assert.equal(call[3].headers['X-Counter-Session'], 'counter-token')
  assert.equal(Object.keys(call[2]).some(key => key.endsWith('From') || key.endsWith('_from')), false)
})

// Both responsive render paths expose the same three metadata fields and dirty-state handler.
test('desktop and mobile Cycle Count views expose editable metadata controls', async () => {
  const source = await readFile(path.join(root, 'src/views/counter/CountingView.vue'), 'utf8')
  for (const field of ['row.productionDate', 'row.expiryDate', 'row.lotNo']) {
    assert.equal(source.split(`v-model="${field}"`).length - 1, 2)
  }
  assert.match(source, /class="metadata-input"[^>]+@(?:input|change)="markEdited\(row\)"/)
  assert.match(source, /class="table-metadata-input"[^>]+@(?:input|change)="markEdited\(row\)"/)
})

// Counters see packing guidance and Total, while variance remains available only in admin reports.
test('counter view hides variance and displays InventoryMaster packing details', async () => {
  const source = await readFile(path.join(root, 'src/views/counter/CountingView.vue'), 'utf8')
  assert.doesNotMatch(source, />Variance</)
  assert.doesNotMatch(source, /actualVariance\(row\)/)
  assert.match(source, /row\.packaging/)
  assert.match(source, /row\.unitsPerPack/)
  assert.match(source, /\/pack/)
  assert.match(source, /function packingIcon\(packaging\)/)
  assert.match(source, /bag\|sack\|pouch/)
  assert.match(source, /box\|carton\|case/)
  assert.match(source, /count-inputs input:invalid,.table-input:invalid/)
})

test('mobile counter starts with a searchable all-product picker', async () => {
  const source = await readFile(path.join(root, 'src/views/counter/CountingView.vue'), 'utf8')
  assert.match(source, /placeholder="Search product name"/)
  assert.match(source, /No products found/)
  assert.match(source, /Try searching for a different product name\./)
  assert.doesNotMatch(source, /No matching products|No product name matches/)
  assert.match(source, /class="product-picker-row"/)
  assert.match(source, /v-if="row\._saved" class="picker-counted"/)
  assert.doesNotMatch(source, />UNCOUNTED</)
  assert.match(source, /function selectMobileProduct\(index\)/)
  assert.match(source, /mobileListOpen\.value = true/)
  assert.doesNotMatch(source, /Count this product and save/)
  assert.doesNotMatch(source, /function showNextNavigationModal/)
  assert.match(source, /@click="changeMobileRow\(1\)"/)
  assert.match(source, /All products have already been counted\./)
  assert.match(source, /Review Counts/)
  assert.match(source, /completedOnOpen\.value = usesMobileProductFlow\(\)/)
  assert.match(source, /navigator\.maxTouchPoints/)
})

// Activity report dates are sent to the shared paginated endpoint and therefore also scope CSV data.
test('activity logs request an inclusive From and To date range', async () => {
  const h = await harness()
  const service = await h.open('src/services/counterAccounts.js')
  await service.getCounterCountLogs({ dateFrom: '2026-09-01', dateTo: '2026-09-11' })
  assert.equal(h.apiCalls[0][0], 'list')
  assert.equal(h.apiCalls[0][1], '/counter-count-logs/?date_from=2026-09-01&date_to=2026-09-11')
})

test('activity report exposes separate raw metadata comparison columns', async () => {
  const source = await readFile(path.join(root, 'src/views/admin/ActivityLogsView.vue'), 'utf8')
  assert.match(source, /<table v-if="activeDateRange" class="raw-report-table">/)
  assert.match(source, /<table v-else class="preview-table">/)
  assert.match(source, /Old Lot No\./)
  assert.match(source, /New Lot No\./)
  assert.match(source, /Old Production Date/)
  assert.match(source, /New Production Date/)
  assert.match(source, /Old Expiration Date/)
  assert.match(source, /New Expiration Date/)
  assert.match(source, /log\.lotNoChanged \? metadataValue\(log\.lotNoFrom\)/)
  assert.match(source, /log\.productionDateChanged \? metadataValue\(log\.productionDateFrom\)/)
  assert.match(source, /log\.expiryDateChanged \? metadataValue\(log\.expiryDateFrom\)/)
})

test('counting warning uses distinct network and WMS server states', async () => {
  const source = await readFile(path.join(root, 'src/layouts/CounterLayout.vue'), 'utf8')
  assert.match(source, /ServerOff/)
  assert.match(source, /<WifiOff v-if="deviceOffline"/)
  assert.match(source, /<ServerOff v-else/)
  assert.match(source, /No network connection\./)
  assert.match(source, /WMS server is unavailable\./)
  assert.match(source, /Contact the IT Department\. Your Cycle Count lock may expire in/)
})

test('failed heartbeat classifies connectivity and only a successful retry restores WMS', async () => {
  let serverAvailable = false
  const h = await harness({
    online: true,
    post: async () => {
      if (!serverAvailable) throw Error('WMS unavailable')
      return { detail: 'Cycle Count lock active.' }
    },
  })
  const session = await h.open('src/services/counterSession.js')
  session.saveCounterSession(7, { token: 'token' })
  const { useCounterLock } = await h.open('src/composables/useCounterLock.js')
  const lock = h.scope.run(() => useCounterLock(ref(7), async () => {}))
  const heartbeat = [...h.intervals.values()][0]

  await heartbeat.callback()
  assert.equal(lock.connectionLost.value, true)
  assert.equal(lock.deviceOffline.value, false)

  await h.listeners.get('online')()
  assert.equal(lock.connectionLost.value, true)

  h.navigator.onLine = false
  await heartbeat.callback()
  assert.equal(lock.connectionLost.value, true)
  assert.equal(lock.deviceOffline.value, true)

  h.navigator.onLine = true
  serverAvailable = true
  await heartbeat.callback()
  assert.equal(lock.connectionLost.value, false)
  assert.equal(lock.deviceOffline.value, false)
  assert.equal(lock.connectionRestored.value, true)
  h.unmount()
})

// Exercise interval ownership, overlap prevention, route changes, and late heartbeat failures.
test('heartbeat and lock countdown timers do not overlap and stop on unmount', async () => {
  const request = deferred()
  const h = await harness({ post: () => request.promise })
  const session = await h.open('src/services/counterSession.js')
  session.saveCounterSession(7, { token: 'token' })
  const { useCounterLock } = await h.open('src/composables/useCounterLock.js')
  const id = ref(7)
  const lock = h.scope.run(() => useCounterLock(id, async () => {}))
  const timer = [...h.intervals.values()][0]
  assert.equal(timer.delay, 3000)
  const pending = timer.callback()
  await timer.callback()
  assert.equal(h.apiCalls.length, 1)
  assert.equal(h.apiCalls[0][1], '/cycle-counts/7/heartbeat/')
  assert.equal(h.apiCalls[0][3].headers['X-Counter-Session'], 'token')
  id.value = undefined
  await nextTick()
  assert.equal(h.intervals.size, 0)
  request.reject(Error('late failure'))
  await pending
  assert.equal(lock.releaseError.value, '')
  id.value = 7
  await nextTick()
  assert.equal(h.intervals.size, 2)
  h.unmount()
  assert.equal(h.intervals.size, 0)
  assert.equal(h.timeouts.size, 0)
  await timer.callback()
  assert.equal(h.apiCalls.length, 1)
})

// Warn after the configured idle delay, continue on user activity, and then unlock.
test('idle counting sessions warn, reset on activity, and return to the list', async () => {
  const h = await harness()
  const session = await h.open('src/services/counterSession.js')
  session.saveCounterSession(7, { token: 'token' })
  const { useCounterLock } = await h.open('src/composables/useCounterLock.js')
  let navigated = 0
  const lock = h.scope.run(() => useCounterLock(ref(7), async () => { navigated++ }))

  const warning = [...h.timeouts.values()].find(timer => timer.delay === 10 * 60 * 1000)
  const exit = [...h.timeouts.values()].find(timer => timer.delay === 15 * 60 * 1000)
  assert.ok(warning)
  assert.ok(exit)
  warning.callback()
  assert.equal(lock.idleWarning.value, true)

  h.listeners.get('pointerdown')()
  assert.equal(lock.idleWarning.value, false)
  const renewedWarning = [...h.timeouts.values()].find(timer => timer.delay === 10 * 60 * 1000)
  const renewedExit = [...h.timeouts.values()].find(timer => timer.delay === 15 * 60 * 1000)
  renewedWarning.callback()
  assert.equal(lock.idleWarning.value, true)
  await renewedExit.callback()
  assert.equal(navigated, 1)
  assert.equal(session.readCounterSession(7), null)
  assert.equal(lock.idleWarning.value, false)
  h.unmount()
})

// Block navigation on failed unlocks and suppress repeated clicks while a release is pending.
test('leave counting waits for unlock and remains retryable after an error', async () => {
  let request = deferred(), navigated = 0
  const h = await harness({ post: () => request.promise })
  const session = await h.open('src/services/counterSession.js')
  session.saveCounterSession(7, { token: 'token' })
  const { useCounterLock } = await h.open('src/composables/useCounterLock.js')
  const lock = h.scope.run(() => useCounterLock(ref(7), async () => { navigated++ }))
  const first = lock.showCycleCounts()
  await lock.showCycleCounts()
  assert.equal(h.apiCalls.length, 1)
  assert.equal(lock.releasing.value, true)
  assert.equal(navigated, 0)
  request.reject(Error('offline'))
  await first
  assert.equal(lock.releaseError.value, 'offline')
  assert.equal(lock.releasing.value, false)
  assert.equal(navigated, 0)
  request = deferred()
  const retry = lock.showCycleCounts()
  request.resolve({})
  await retry
  assert.equal(navigated, 1)
  assert.equal(session.readCounterSession(7), null)
  h.unmount()
})

// Focus, interval, and manual refreshes must share one pending request and recover after failure.
test('selection refreshes never overlap and recover without clearing cards', async () => {
  let request = deferred()
  const h = await harness({ list: () => request.promise })
  const page = await h.open('src/views/counter/SelectWarehouseView.vue')
  const initial = page.loadCycleCounts()
  await page.refreshCycleCounts()
  await page.loadCycleCounts()
  assert.equal(h.apiCalls.filter(call => call[0] === 'list').length, 1)
  request.resolve([{ id: 7, ccType: 'D', statusId: 0 }])
  await initial
  assert.equal(page.selectedCycleCountId.value, '7')
  request = deferred()
  const refresh = page.refreshCycleCounts()
  await page.refreshCycleCounts()
  request.reject(Error('offline'))
  await refresh
  assert.equal(page.cycleCounts.value[0].id, 7)
  request = deferred()
  const retry = page.refreshCycleCounts()
  request.resolve([{ id: 8 }])
  await retry
  assert.equal(page.cycleCounts.value[0].id, 8)
  assert.equal(h.apiCalls.filter(call => call[0] === 'list').length, 3)
  h.unmount()
})

// Leaving during the initial load must not create an orphan timer or attach event listeners.
test('selection unmount during initial load prevents late updates and timers', async () => {
  const request = deferred()
  const h = await harness({ list: () => request.promise })
  const page = await h.open('src/views/counter/SelectWarehouseView.vue')
  const mounting = h.mounted[0]()
  h.unmount()
  request.resolve([{ id: 7, ccType: 'D', statusId: 0 }])
  await mounting
  assert.equal(page.cycleCounts.value.length, 0)
  assert.equal(h.intervals.size, 0)
  assert.equal(h.listeners.size, 0)
  await page.refreshCycleCounts()
  assert.equal(h.apiCalls.filter(call => call[0] === 'list').length, 1)
})

// Preserve the 1.5-second refresh cadence and clean up all listeners after a completed mount.
test('selection cleanup removes timers and ignores a pending refresh response', async () => {
  let request = deferred()
  const h = await harness({ list: () => request.promise })
  const page = await h.open('src/views/counter/SelectWarehouseView.vue')
  request.resolve([{ id: 7, ccType: 'D', statusId: 0 }])
  await h.mounted[0]()
  assert.equal([...h.intervals.values()][0].delay, 1500)
  assert.equal(h.listeners.size, 2)
  request = deferred()
  const pending = page.refreshCycleCounts()
  h.unmount()
  request.resolve([{ id: 8 }])
  await pending
  assert.equal(page.cycleCounts.value[0].id, 7)
  assert.equal(h.intervals.size, 0)
  assert.equal(h.listeners.size, 0)
})

// A refreshed card list must not change the ID used for an in-progress verification and navigation.
test('verification retains the chosen count and prevents duplicate submissions', async () => {
  const request = deferred()
  const h = await harness({ post: () => request.promise })
  const page = await h.open('src/views/counter/SelectWarehouseView.vue')
  page.cycleCounts.value = [{ id: 7, code: 'CC7', ccType: 'D', statusId: 0 }]
  page.selectedCycleCountId.value = '7'
  page.selectedCounterId.value = '2'
  page.accessCode.value = '1111'
  const pending = page.openCycleCount()
  await page.openCycleCount()
  page.cycleCounts.value = []
  request.resolve({ token: 'token', cycleCountId: 7 })
  await pending
  const verificationCalls = h.apiCalls.filter(call => call[0] === 'post' && call[1] === '/counter-access/verify/')
  const detailCalls = h.apiCalls.filter(call => call[0] === 'get' && call[1] === '/cycle-counts/7/details/')
  assert.equal(verificationCalls.length, 1)
  assert.equal(detailCalls.length, 1)
  assert.equal(verificationCalls[0][2].cycleCountId, 7)
  assert.equal(verificationCalls[0][2].counterId, '2')
  assert.equal(verificationCalls[0][2].accessCode, '1111')
  assert.equal(JSON.parse(h.storage.get('wms-counter-session-7')).token, 'token')
  assert.equal(h.navigations[0].path, '/counter/count/7')
  assert.equal(page.accessCode.value, '')
  h.unmount()
})
