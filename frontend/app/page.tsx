"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { login } from "@/lib/api"

export default function LoginPage() {
  const [code, setCode] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState("")
  const router = useRouter()

  const handleLogin = async (type: "admin" | "user") => {
    if (!code.trim()) return

    setIsLoading(true)
    setError("")

    const result = await login(code.trim())

    if (result.success && result.data) {
      // 로그인 성공 - localStorage에 정보 저장
      localStorage.setItem("accessCode", code)
      localStorage.setItem("userId", result.data.user_id.toString())
      localStorage.setItem("userType", result.data.user_type)
      localStorage.setItem("userName", result.data.name)
      localStorage.setItem("token", result.data.token)

      const destination = result.data.user_type === "admin" ? "/admin" : "/user"
      router.push(destination)
    } else {
      // 로그인 실패
      setError(result.error || "로그인에 실패했습니다")
      setIsLoading(false)
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
                if (e.key === "Enter" && code.trim() && !isLoading) {
                  handleLogin("admin")
                }
              }}
              disabled={isLoading}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>

          <div className="space-y-3">
            <Button
              onClick={() => handleLogin("admin")}
              disabled={!code.trim() || isLoading}
              className="w-full h-12 text-base font-medium"
            >
              {isLoading ? "로그인 중..." : "관계자로 로그인"}
            </Button>
            <Button
              onClick={() => handleLogin("user")}
              disabled={!code.trim() || isLoading}
              variant="outline"
              className="w-full h-12 text-base font-medium"
            >
              {isLoading ? "로그인 중..." : "사용자로 로그인"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
