<script setup>
import { onMounted, reactive, ref } from 'vue'
import { AlertCircle, Eye, EyeOff, Hash, KeyRound, LoaderCircle, Pencil, Plus, Power, Save, ShieldCheck, Trash2, UserRound, UsersRound, X } from 'lucide-vue-next'
import { createCounterAccount, deleteCounterAccount, getCounterAccounts, updateCounterAccount } from '../../services/counterAccounts'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const accounts = ref([])
const loading = ref(true)
const saving = ref(false)
const editingId = ref(null)
const error = ref('')
const loadError = ref('')
const success = ref('')
const showPassword = ref(false)
const form = reactive({ counterNumber: '', name: '', role: 'counter', username: '', password: '', accessCode: '' })
// Convert a role into its display label. Troubleshoot: admin/counter values returned by the backend.
const roleLabel = role => ({ admin: 'Administrator', counter: 'Counter' }[role] || 'Account')

// Reset the account form and editing ID. Troubleshoot: stale form values after saving or cancelling.
function resetForm() {
  editingId.value = null
  showPassword.value = false
  Object.assign(form, { counterNumber: '', name: '', role: 'counter', username: '', password: '', accessCode: '' })
}

// Copy the account into the edit form and scroll to the top. Troubleshoot: editingId and field mapping.
function editAccount(account) {
  resetForm()
  editingId.value = account.id
  Object.assign(form, { counterNumber: String(account.counterNumber), name: account.name, role: account.role, username: account.username || '' })
  error.value = ''
  success.value = ''
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// Load the account list from the API. Troubleshoot: getCounterAccounts and loading/error state.
async function loadAccounts() {
  loading.value = true
  loadError.value = ''
  try {
    accounts.value = await getCounterAccounts()
  } catch (requestError) {
    loadError.value = requestError.message
  } finally {
    loading.value = false
  }
}

// Validate and save the account form, then update the list and session. Troubleshoot: role fields, API errors, and ownCredentialsChanged.
async function saveAccount() {
  error.value = ''
  success.value = ''
  const editing = editingId.value !== null
  if (!form.name.trim()) {
    error.value = 'Enter the employee name.'
    return
  }
  const changes = { name: form.name.trim(), role: form.role }
  if (form.role === 'counter') {
    if ((!editing || form.accessCode) && !/^[0-9]{4}$/.test(form.accessCode)) {
      error.value = 'Access code must contain exactly 4 digits.'
      return
    }
    if (editing) {
      if (!/^[0-9]+$/.test(form.counterNumber) || Number(form.counterNumber) < 1) {
        error.value = 'Counter number must be 1 or higher.'
        return
      }
      changes.counterNumber = Number(form.counterNumber)
    }
    if (form.accessCode) changes.accessCode = form.accessCode
  } else {
    changes.username = form.username.trim().toLowerCase()
    if (!changes.username || (!editing && !form.password)) {
      error.value = 'Enter a username and password for the staff account.'
      return
    }
    if (form.password) changes.password = form.password
  }
  saving.value = true
  try {
    const account = editing
      ? await updateCounterAccount(editingId.value, changes)
      : await createCounterAccount(changes)
    // Find the saved account's index in the displayed list. Troubleshoot: item.id and account.id matching.
    const index = accounts.value.findIndex(item => item.id === account.id)
    if (index >= 0) accounts.value[index] = account
    else accounts.value.push(account)
    // Sort accounts alphabetically by name using localeCompare.
    accounts.value.sort((a, b) => a.name.localeCompare(b.name))
    const ownCredentialsChanged = account.id === auth.user?.id && (changes.password || changes.username !== auth.user.username)
    resetForm()
    success.value = `${roleLabel(account.role)} ${account.name} was ${editing ? 'updated' : 'created'}.`
    if (ownCredentialsChanged) {
      window.dispatchEvent(new Event('wms-session-expired'))
    } else if (account.id === auth.user?.id) {
      auth.user.name = account.name
    }
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    saving.value = false
  }
}

// Activate or deactivate an account through the API. Troubleshoot: active payload and self-deactivation validation.
async function toggleAccount(account) {
  account._saving = true
  error.value = ''
  success.value = ''
  try {
    const updated = await updateCounterAccount(account.id, { active: !account.active })
    Object.assign(account, updated)
    success.value = `${account.name} is now ${account.active ? 'active' : 'inactive'}.`
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    account._saving = false
  }
}

// Confirm deletion and remove the account from the API and list. Troubleshoot: account ID and backend HTTP 409 responses.
async function deleteAccount(account) {
  if (!window.confirm(`Delete ${roleLabel(account.role)} ${account.name}?`)) return
  account._saving = true
  error.value = ''
  success.value = ''
  try {
    await deleteCounterAccount(account.id)
    // Remove the deleted account from the displayed list by ID.
    accounts.value = accounts.value.filter(item => item.id !== account.id)
    if (editingId.value === account.id) resetForm()
    success.value = `${account.name} was deleted.`
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    account._saving = false
  }
}

onMounted(loadAccounts)
</script>

<template>
  <main class="page user-page">
    <div class="page-header">
      <div class="page-title-group"><div class="page-title-icon"><UsersRound :size="22" /></div><div><h1 class="page-title">User Management</h1><p class="page-subtitle">Manage Administrator and Counter access.</p></div></div>
    </div>
    <div class="user-layout">
      <section class="card create-card" aria-labelledby="account-form-heading">
        <div class="section-heading">
          <div class="heading-icon"><Pencil v-if="editingId" :size="21" /><Plus v-else :size="21" /></div>
          <div><h2 id="account-form-heading">{{ editingId ? 'Edit account' : 'Add account' }}</h2><p>Counters use an access code. Staff use a username and password.</p></div>
        </div>
        <form class="counter-form" @submit.prevent="saveAccount">
          <fieldset :disabled="saving" class="account-fields">
            <label><span class="label">Role</span><select v-model="form.role" class="select" :disabled="!!editingId"><option value="counter">Counter</option><option value="admin">Administrator</option></select><small v-if="editingId" class="code-note">Create a separate account to assign a different role.</small></label>
            <label v-if="editingId && form.role === 'counter'"><span class="label">Counter number</span><div class="field-icon"><Hash :size="17" /><input v-model="form.counterNumber" type="number" class="input" min="1" step="1" required /></div></label>
            <label><span class="label">Employee name</span><div class="field-icon"><UserRound :size="17" /><input v-model="form.name" class="input" maxlength="150" autocomplete="name" required /></div></label>
            <label v-if="form.role === 'counter'"><span class="label">{{ editingId ? 'New 4-digit code (optional)' : '4-digit access code' }}</span><div class="field-icon"><KeyRound :size="17" /><input v-model="form.accessCode" type="password" class="input code-input" inputmode="numeric" maxlength="4" autocomplete="new-password" :required="!editingId" @input="form.accessCode = form.accessCode.replace(/\D/g, '').slice(0, 4)" /></div><small class="code-note"><ShieldCheck :size="14" />{{ editingId ? 'Leave blank to keep the current code.' : 'Access codes are stored securely.' }}</small></label>
            <template v-else>
              <label><span class="label">Username</span><input v-model="form.username" class="input" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="150" required /></label>
              <label><span class="label">{{ editingId ? 'New password (optional)' : 'Password' }}</span><div class="password-input"><input v-model="form.password" :type="showPassword ? 'text' : 'password'" class="input" autocomplete="new-password" maxlength="128" :required="!editingId" /><button type="button" :aria-label="showPassword ? 'Hide password' : 'Show password'" @click="showPassword = !showPassword"><EyeOff v-if="showPassword" :size="17" /><Eye v-else :size="17" /></button></div><small class="code-note">Changing credentials ends existing sessions.</small></label>
            </template>
          </fieldset>
          <p v-if="error && !loading" class="form-message error" role="alert">{{ error }}</p>
          <p v-if="success" class="form-message success" role="status" aria-live="polite">{{ success }}</p>
          <div class="form-actions"><button class="btn btn-primary create-button" type="submit" :disabled="saving"><LoaderCircle v-if="saving" class="spin" :size="19" /><Save v-else :size="19" />{{ saving ? 'Saving...' : editingId ? 'Update account' : 'Create account' }}</button><button v-if="editingId" class="btn cancel-button" type="button" :disabled="saving" @click="resetForm"><X :size="18" />Cancel</button></div>
        </form>
      </section>
      <section class="card users-card" aria-labelledby="account-list-heading">
        <div class="list-heading"><div><h2 id="account-list-heading">Accounts</h2><p>{{ accounts.length }} account(s)</p></div><UsersRound :size="23" /></div>
        <div v-if="loading" class="list-state"><LoaderCircle class="spin" :size="25" />Loading accounts...</div>
        <div v-else-if="loadError && !accounts.length" class="list-state list-error" role="alert"><AlertCircle :size="25" /><span>{{ loadError }}</span><button class="btn btn-secondary" type="button" @click="loadAccounts">Try again</button></div>
        <div v-else-if="accounts.length" class="user-list">
          <article v-for="account in accounts" :key="account.id" class="user-row">
            <div class="avatar">{{ account.name.charAt(0).toUpperCase() }}</div>
            <div class="user-info"><strong>{{ account.name }}</strong><span>{{ roleLabel(account.role) }} · {{ account.role === 'counter' ? `Counter ${account.counterNumber}` : account.username }}</span></div>
            <div class="account-state"><span :class="['badge', account.active ? 'badge-green' : 'badge-slate']">{{ account.active ? 'Active' : 'Inactive' }}</span><div class="account-actions"><button type="button" class="edit-button" :disabled="account._saving || saving" @click="editAccount(account)"><Pencil :size="16" />Edit</button><button type="button" :class="{ inactive: !account.active }" :disabled="account._saving || saving || account.id === auth.user?.id" @click="toggleAccount(account)"><LoaderCircle v-if="account._saving" class="spin" :size="16" /><Power v-else :size="16" />{{ account._saving ? 'Saving...' : account.active ? 'Deactivate' : 'Activate' }}</button><button type="button" class="delete-button" :disabled="account._saving || saving || account.id === auth.user?.id" @click="deleteAccount(account)"><Trash2 :size="16" />Delete</button></div></div>
          </article>
        </div>
        <p v-else class="empty-users">No accounts found.</p>
      </section>
    </div>
  </main>
</template>

<style scoped>
.account-fields{border:0;padding:0;margin:0;display:grid;gap:16px;min-width:0}

.user-page{max-width:1400px;margin:0 auto}.user-layout{display:grid;grid-template-columns:minmax(330px,440px) minmax(0,1fr);gap:18px;align-items:start}.create-card{padding:22px}.section-heading{display:flex;gap:11px;align-items:center;margin-bottom:20px}.heading-icon{width:42px;height:42px;border-radius:12px;background:#e8f7ec;color:#166534;display:grid;place-items:center}.section-heading h2,.list-heading h2{margin:0;font-size:20px}.section-heading p,.list-heading p{margin:3px 0 0;color:#64748b;font-size:13px}.counter-form{display:grid;gap:16px}.field-icon{position:relative}.field-icon svg{position:absolute;left:12px;top:50%;transform:translateY(-50%);color:#64748b}.field-icon .input{padding-left:39px;font-size:16px}.password-input{position:relative}.password-input .input{padding-right:50px}.password-input button{position:absolute;right:2px;top:50%;width:44px;height:44px;transform:translateY(-50%);border:0;border-radius:8px;background:transparent;color:#64748b;display:grid;place-items:center}.password-input button:hover{background:#edf7ef;color:#166534}.code-input{letter-spacing:.2em;font-weight:900}.code-note{display:flex;align-items:center;gap:5px;margin-top:6px;color:#64748b;font-size:11px}.form-message{margin:0;padding:10px 12px;border-radius:9px;font-size:13px;font-weight:700}.form-message.error{background:#fef2f2;color:#b91c1c}.form-message.success{background:#f0fdf4;color:#166534}.form-actions{display:flex;gap:8px}.create-button{min-height:46px;flex:1}.cancel-button{min-height:46px;border:1px solid #d9e2dc;background:#fff;color:#475569;display:inline-flex;align-items:center;justify-content:center;gap:6px}.users-card{overflow:hidden}.list-heading{display:flex;justify-content:space-between;align-items:center;padding:19px 20px;border-bottom:1px solid #e5ebe6;color:#334155}.list-state{min-height:150px;display:flex;align-items:center;justify-content:center;gap:8px;color:#64748b}.list-state.list-error{flex-direction:column;padding:24px;text-align:center;color:#b91c1c}.user-list{display:grid}.user-row{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:center;padding:16px 20px;border-bottom:1px solid #edf1ed}.user-row:last-child{border-bottom:0}.avatar{width:43px;height:43px;border-radius:12px;background:#e8f7ec;color:#166534;display:grid;place-items:center;font-size:18px;font-weight:900}.user-info{min-width:0}.user-info>strong,.user-info>span{display:block}.user-info>span{font-size:12px;color:#64748b;margin-top:3px;overflow-wrap:anywhere}.account-state{text-align:right}.account-state>span{margin-bottom:7px}.account-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}.account-state button{min-height:40px;border:1px solid #fecaca;border-radius:8px;background:#fff;color:#b91c1c;display:flex;align-items:center;gap:5px;padding:7px 9px;font-size:12px;font-weight:800}.account-state button.edit-button{border-color:#bbf7d0;color:#166534}.account-state button.inactive{border-color:#bbf7d0;color:#166534}.account-state button.delete-button{border-color:#e2e8f0;color:#475569}.account-state button:disabled{opacity:.55}.empty-users{padding:36px 20px;text-align:center;color:#64748b}
@media(max-width:1050px){.user-layout{grid-template-columns:1fr}.create-card{max-width:none}}@media(max-width:600px){.user-page{padding:14px}.create-card{padding:16px}.user-row{grid-template-columns:auto minmax(0,1fr);padding:14px}.account-state{grid-column:1/-1;display:grid;gap:9px;text-align:left}.account-state>span{width:max-content;margin:0}.account-actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));width:100%}.account-state button{justify-content:center;padding-inline:6px}}
@media(max-width:380px){.account-actions{grid-template-columns:1fr}.account-state button{min-height:44px}}
</style>
