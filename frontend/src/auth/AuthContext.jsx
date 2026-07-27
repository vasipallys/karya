import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { can as roleCan } from './permissions'

const STORAGE_KEY = 'karya.auth.user'
const AuthContext = createContext(null)

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

/**
 * Local demo auth: the signed-in "user" is a person from the resource directory
 * plus a role. There are no passwords/tokens — the session is kept client-side
 * and the role gates the UI. `user` shape: { staff_id, name, role, staff_code }.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(loadStored)

  useEffect(() => {
    if (user) localStorage.setItem(STORAGE_KEY, JSON.stringify(user))
    else localStorage.removeItem(STORAGE_KEY)
  }, [user])

  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener('karya:unauthorized', onUnauthorized)
    return () => window.removeEventListener('karya:unauthorized', onUnauthorized)
  }, [])

  const signIn = useCallback((nextUser) => setUser(nextUser), [])
  const signOut = useCallback(() => setUser(null), [])

  const refreshAccess = useCallback(() => {
    if (!user?.staff_id || !api.myAccess) return Promise.resolve()
    return api.myAccess().then((access) => setUser((current) => current?.staff_id === access.id ? {
      ...current, role: access.role, page_permissions: access.page_permissions,
    } : current)).catch(() => {})
  }, [user?.staff_id])

  useEffect(() => {
    if (!user?.staff_id) return undefined
    refreshAccess()
    window.addEventListener('focus', refreshAccess)
    return () => window.removeEventListener('focus', refreshAccess)
  }, [user?.staff_id, refreshAccess])

  const value = useMemo(() => ({
    user,
    role: user?.role || null,
    signIn,
    signOut,
    can: (capability) => (user ? roleCan(user.role, capability, user.page_permissions) : false),
    refreshAccess,
  }), [user, signIn, signOut, refreshAccess])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
