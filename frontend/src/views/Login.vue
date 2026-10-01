<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 style="text-align: center">卷王之王</h2>
      <el-form @submit.prevent="doLogin">
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="请输入访问密码" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" style="width: 100%" native-type="submit" :loading="loading">
            登录
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, errMsg } from '../api'

const password = ref('')
const loading = ref(false)
const router = useRouter()

async function doLogin() {
  loading.value = true
  try {
    const { data } = await api.post('/auth/login', { password: password.value })
    localStorage.setItem('sa_token', data.token)
    router.replace('/')
  } catch (e) {
    alert(errMsg(e))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
}
.login-card {
  width: 320px;
}
</style>
