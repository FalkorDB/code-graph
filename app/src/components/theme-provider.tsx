import { createContext, useContext, useEffect, useState } from "react"

type Theme = "dark" | "light" | "system"
type ResolvedTheme = Exclude<Theme, "system">

type ThemeProviderState = {
  theme: Theme
  resolvedTheme: ResolvedTheme
  setTheme: (theme: Theme) => void
}

const VALID_THEMES: Theme[] = ["light", "dark", "system"]

const ThemeProviderContext = createContext<ThemeProviderState | undefined>(undefined)

const MEDIA_QUERY = "(prefers-color-scheme: dark)"

const getSystemTheme = (): ResolvedTheme =>
  typeof window !== "undefined" && window.matchMedia(MEDIA_QUERY).matches ? "dark" : "light"

export function ThemeProvider({
  children,
  defaultTheme = "system",
  storageKey = "code-graph-theme",
}: {
  children: React.ReactNode
  defaultTheme?: Theme
  storageKey?: string
}) {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem(storageKey)
    return stored && VALID_THEMES.includes(stored as Theme) ? (stored as Theme) : defaultTheme
  })
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(getSystemTheme)

  useEffect(() => {
    const mediaQuery = window.matchMedia(MEDIA_QUERY)
    const updateSystemTheme = () => setSystemTheme(mediaQuery.matches ? "dark" : "light")

    updateSystemTheme()
    mediaQuery.addEventListener("change", updateSystemTheme)

    return () => mediaQuery.removeEventListener("change", updateSystemTheme)
  }, [])

  useEffect(() => {
    const root = window.document.documentElement
    root.classList.remove("light", "dark")

    root.classList.add(theme === "system" ? systemTheme : theme)
  }, [theme, systemTheme])

  const value = {
    theme,
    resolvedTheme: theme === "system" ? systemTheme : theme,
    setTheme: (theme: Theme) => {
      localStorage.setItem(storageKey, theme)
      setTheme(theme)
    },
  }

  return (
    <ThemeProviderContext.Provider value={value}>
      {children}
    </ThemeProviderContext.Provider>
  )
}

export const useTheme = () => {
  const context = useContext(ThemeProviderContext)
  if (context === undefined) throw new Error("useTheme must be used within a ThemeProvider")
  return context
}
