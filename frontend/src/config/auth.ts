import { appConfig } from './app'

const KEY = 'cce_demo_authenticated'

export const auth = {
  isAuthenticated() { return localStorage.getItem(KEY) === 'true' },
  login(username: string, password: string) {
    if (username === appConfig.demoUsername && password === appConfig.demoPassword) {
      localStorage.setItem(KEY, 'true')
      return true
    }
    return false
  },
  logout() { localStorage.removeItem(KEY) },
}
