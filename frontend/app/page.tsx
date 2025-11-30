"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { apiPost } from "@/lib/api"

export default function LoginPage() {
  const [code, setCode] = useState("")
  const router = useRouter()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleLogin = async (type: "admin" | "user") => {
    if (!code.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await apiPost<{
        access_token: string
        token_type: string
        user: any
      }>("/auth/login", { access_code: code.trim().toUpperCase() })

      // Store token and basic user info
      localStorage.setItem("accessToken", res.access_token)
      localStorage.setItem("tokenType", res.token_type)
      localStorage.setItem("accessCode", code.trim().toUpperCase())
      localStorage.setItem("currentUser", JSON.stringify(res.user))

      router.push(`/${type}`)
    } catch (e: any) {
      setError(e?.message || "로그인에 실패했습니다")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background via-secondary/30 to-accent/20 p-4">
      <Card className="w-full max-w-md shadow-xl">
        <CardHeader className="space-y-3 text-center">
          <div className="mx-auto w-16 h-16 bg-primary rounded-2xl flex items-center justify-center mb-2">
            <svg
              className="w-10 h-10 text-primary-foreground"
              fill="none"
              strokeWidth="2"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"
              />
            </svg>
          </div>
          <CardTitle className="text-3xl font-bold">온보딩 플랫폼</CardTitle>
          <CardDescription className="text-base">코드를 입력하여 로그인하세요</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <label htmlFor="code" className="text-sm font-medium">
              접속 코드
            </label>
            <Input
              id="code"
              type="text"
              placeholder="코드를 입력하세요"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="h-12"
              onKeyDown={(e) => {
                if (e.key === "Enter" && code.trim()) {
                  handleLogin("admin")
                }
              }}
            />
            {error && <p className="text-sm text-red-500">{error}</p>}
          </div>

          <div className="space-y-3">
            <Button
              onClick={() => handleLogin("admin")}
              disabled={!code.trim()}
              className="w-full h-12 text-base font-medium"
            >
              {loading ? "로그인 중..." : "관계자로 로그인"}
            </Button>
            <Button
              onClick={() => handleLogin("user")}
              disabled={!code.trim()}
              variant="outline"
              className="w-full h-12 text-base font-medium"
            >
              {loading ? "로그인 중..." : "사용자로 로그인"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
