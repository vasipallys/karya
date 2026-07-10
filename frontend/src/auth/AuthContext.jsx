import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { can as roleCan } from './permissions'

const STORAGE_KEY = 'storypointer.auth.user'
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

  const signIn = useCallback((nextUser) => setUser(nextUser), [])
  const signOut = useCallback(() => setUser(null), [])

  const value = useMemo(() => ({
    user,
    role: user?.role || null,
    signIn,
    signOut,
    can: (capability) => (user ? roleCan(user.role, capability) : false),
  }), [user, signIn, signOut])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
