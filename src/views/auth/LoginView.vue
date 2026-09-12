<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Eye, EyeOff, UserRound, LockKeyhole } from 'lucide-vue-next'
import { useAuthStore } from '../../stores/auth'
import csIcon from '../../assets/CS_ICO.ico'

const username = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref('')
const submitting = ref(false)
const auth = useAuthStore()
const router = useRouter()

// On mount, apply page CSS classes to html/body. Troubleshoot: mobile sizing and scrolling.
onMounted(() => {
  document.documentElement.classList.add('signin-active')
  document.body.classList.add('signin-active')
})

// On unmount, remove page CSS classes and clear timers where applicable.
onUnmounted(() => {
  document.documentElement.classList.remove('signin-active')
  document.body.classList.remove('signin-active')
})

// Submit the login form and navigate to the administrator page. Troubleshoot: auth.login, credentials, and the error message.
async function submit() {
  error.value = ''
  submitting.value = true
  try {
    await auth.login({ username: username.value, password: password.value })
    password.value = ''
    await router.push('/admin/cycle-counts')
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="brand-panel">
      <div class="brand-mark"><img :src="csIcon" alt="" /></div>
      <div>
        <div class="eyebrow">WMS</div>
        <h1>Cycle Count</h1>
      </div>

    </section>

    <section class="login-card card">
      <div class="login-heading">
        <div class="brand-mark small"><img :src="csIcon" alt="" /></div>
        <div>
          <h2> Sign in</h2>
          <p class="muted">Administrator</p>
        </div>
      </div>

      <form class="form-stack" :aria-busy="submitting" @submit.prevent="submit">
        <label>
          <span class="label">User name</span>
          <div class="icon-input"><UserRound :size="18" /><input v-model.trim="username" class="input" autocomplete="username" autocapitalize="none" spellcheck="false" required /></div>
        </label>
        <label>
          <span class="label">Password</span>
          <div class="icon-input"><LockKeyhole :size="18" /><input v-model="password" :type="showPassword ? 'text' : 'password'" class="input" autocomplete="current-password" required /><button class="password-toggle" type="button" :aria-label="showPassword ? 'Hide password' : 'Show password'" @click="showPassword = !showPassword"><EyeOff v-if="showPassword" :size="18" /><Eye v-else :size="18" /></button></div>
        </label>
        <p v-if="error" class="login-error" role="alert" aria-live="assertive">{{ error }}</p>
        <button class="btn btn-primary submit" type="submit" :disabled="submitting">{{ submitting ? 'Signing in…' : 'Sign in' }}</button>
<RouterLink class="counter-link" to="/counter/cycle-counts">

  <span>Back to Cycle Counts</span>
</RouterLink>
      </form>
    </section>
  </main>
</template>

<style scoped>
.login-page{min-height:100vh;min-height:100dvh;display:grid;grid-template-columns:minmax(0,1.05fr) minmax(440px,.95fr);background:linear-gradient(135deg,#ecf7ee,#f7faf7)}
.brand-panel{padding:72px;display:flex;flex-direction:column;justify-content:center;gap:28px;background:linear-gradient(145deg,rgba(5,46,22,.9),rgba(20,83,45,.82)),url('../../assets/warehouse-login-bg.jpg') center/cover no-repeat;color:white}
.brand-mark{width:62px;height:62px;border-radius:18px;display:grid;place-items:center;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.18)}
.brand-mark img{width:44px;height:44px;object-fit:contain}.brand-mark.small img{width:34px;height:34px}
.brand-mark.small{width:48px;height:48px;border-radius:14px;background:#e8f7ec;color:#166534;border:0}
.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:12px;font-weight:800;color:#bbf7d0}
h1{font-size:54px;line-height:1.05;margin:8px 0 14px;max-width:560px}.brand-panel p{font-size:18px;max-width:560px;color:#d1fae5;line-height:1.65}.trust{display:flex;gap:10px;align-items:center;color:#dcfce7;font-weight:700}
.login-card{align-self:center;justify-self:center;width:min(470px,calc(100% - 40px));padding:32px}.login-heading{display:flex;gap:14px;align-items:center;margin-bottom:26px}.login-heading h2{margin:0;font-size:28px}.login-heading p{margin:4px 0 0}.form-stack{display:grid;gap:18px}.icon-input{position:relative;isolation:isolate}.icon-input svg{position:absolute;z-index:1;pointer-events:none;left:12px;top:50%;transform:translateY(-50%);color:#64748b}.icon-input .input{min-height:46px;padding-left:40px}.icon-input:has(.password-toggle) .input{padding-right:50px}.password-toggle{position:absolute;z-index:2;right:2px;top:50%;width:44px;height:44px;transform:translateY(-50%);border:0;border-radius:8px;background:transparent;color:#64748b;display:grid;place-items:center}.password-toggle:hover{background:#edf7ef;color:#166534}.password-toggle svg{position:static;pointer-events:auto;transform:none;left:auto;top:auto;color:currentColor}.login-error{margin:0;padding:10px 12px;border-radius:9px;background:#fef2f2;color:#b91c1c;font-size:13px;font-weight:700}.submit{width:100%;margin-top:4px;padding:13px}
.counter-link{text-align:center;color:#166534;font-size:13px;font-weight:800;text-decoration:none}.counter-link:hover{text-decoration:underline}
@media(max-width:900px){.login-page{grid-template-columns:1fr}.brand-panel{display:none}.login-card{margin:40px auto}}
</style>

<style scoped>
/* Lightweight visual effects; motion is disabled below when the user requests it. */
.login-page{position:relative;overflow:hidden;isolation:isolate}
.login-page::before,.login-page::after{content:"";position:absolute;z-index:-1;border-radius:999px;pointer-events:none;filter:blur(2px)}
.login-page::before{width:420px;height:420px;right:-160px;top:-150px;background:radial-gradient(circle,rgba(34,197,94,.18),rgba(34,197,94,0) 68%)}
.login-page::after{width:360px;height:360px;left:42%;bottom:-220px;background:radial-gradient(circle,rgba(20,83,45,.12),rgba(20,83,45,0) 70%)}
.brand-panel{position:relative;overflow:hidden;isolation:isolate}
.brand-panel>div:not(.trust){animation:brand-reveal .2s ease-out backwards}
.brand-mark{box-shadow:0 12px 30px rgba(4,47,23,.16)}
.brand-mark.small{box-shadow:0 10px 24px rgba(22,101,52,.12)}
.login-card{position:relative;z-index:1;animation:card-reveal .2s ease-out backwards;transition:box-shadow .2s ease}
.login-card:hover{box-shadow:0 14px 36px rgba(15,23,42,.09)}
.icon-input svg{transition:color .2s ease,transform .2s ease}
.icon-input:focus-within svg{color:#15803d;transform:translateY(-50%) scale(1.08)}
.icon-input .input,.form-stack .select{font-size:16px;transition:border-color .2s ease,box-shadow .2s ease,transform .2s ease}
.icon-input .input:focus,.form-stack .select:focus{border-color:#22a447;outline:none;box-shadow:0 0 0 4px rgba(22,163,74,.12);transform:translateY(-1px)}
.submit{position:relative;overflow:hidden;min-height:48px;transition:transform .18s ease,box-shadow .2s ease,background-color .2s ease}
.submit:hover{transform:translateY(-1px);box-shadow:0 8px 18px rgba(20,83,45,.2)}
.submit:active{transform:translateY(0) scale(.99)}
@keyframes card-reveal{from{opacity:0;transform:translateY(18px) scale(.985)}to{opacity:1;transform:none}}
@keyframes brand-reveal{from{opacity:0;transform:translateX(-18px)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){.login-page::before,.login-page::after,.brand-panel::after,.brand-panel>div,.brand-mark,.login-card,.form-stack>label,.form-stack>.login-error,.form-stack>.submit{animation:none!important}.form-stack>label,.form-stack>.login-error,.form-stack>.submit{opacity:1}.login-card,.submit,.icon-input .input,.form-stack .select{transition:none}}
@media(max-width:767px){:global(html.signin-active),:global(body.signin-active),:global(html.signin-active #app){width:100%;min-height:100%;margin:0}.login-page{width:100%;min-height:100vh;min-height:100dvh;padding:clamp(12px,4vw,24px);display:flex;align-items:center;justify-content:center;overflow-y:auto}.brand-panel{display:none}.login-card{width:min(470px,100%);margin:auto;padding:clamp(20px,6vw,30px)}.login-heading{margin-bottom:22px}}
@media(max-height:560px){.login-page{align-items:flex-start}.login-card{margin-block:12px}.login-heading{margin-bottom:16px}.form-stack{gap:13px}}
</style>
