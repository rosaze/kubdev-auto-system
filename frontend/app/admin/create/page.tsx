"use client"

import { useEffect, useState, useRef } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { createAdminAccount, createUserAccount, createUserWithEnvironmentStream, type StreamEvent } from "@/lib/api"

export default function AdminCreatePage() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [accountType, setAccountType] = useState<"admin" | "user" | null>(null)
  const [isEnvironmentSet, setIsEnvironmentSet] = useState(false)

  const [userId, setUserId] = useState("")
  const [selectedTemplate, setSelectedTemplate] = useState<number>(3) // 기본값: demo_bash_simple

  const [generatedAccount, setGeneratedAccount] = useState<{
    type: "admin" | "user"
    code: string
    userId?: string
    environmentId?: number
  } | null>(null)

  const [isCreating, setIsCreating] = useState(false)
  const [createError, setCreateError] = useState("")
  const [logs, setLogs] = useState<string[]>([])
  const [showLogs, setShowLogs] = useState(false)
  const closeStreamRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    setMounted(true)
    const code = localStorage.getItem("accessCode")
    if (!code) {
      router.push("/")
      return
    }

    const savedEnvironment = localStorage.getItem("environmentSet")
    if (savedEnvironment === "true") {
      setIsEnvironmentSet(true)
    }
  }, [router])

  const handleCreateAdminAccount = async () => {
    const currentUserId = localStorage.getItem("userId")
    if (!currentUserId) {
      setCreateError("사용자 정보를 찾을 수 없습니다. 다시 로그인해주세요.")
      return
    }

    setIsCreating(true)
    setCreateError("")

    const result = await createAdminAccount(currentUserId)

    if (result.success && result.data) {
      setGeneratedAccount({
        type: "admin",
        code: result.data.user_code,
      })
    } else {
      setCreateError(result.error || "계정 생성에 실패했습니다")
    }

    setIsCreating(false)
  }

  const handleCreateUserAccount = async () => {
    if (!userId.trim()) {
      setCreateError("사용자 이름을 입력해주세요.")
      return
    }

    setIsCreating(true)
    setCreateError("")
    setLogs([])
    setShowLogs(true)

    // SSE를 사용한 실시간 로그 스트리밍
    const closeStream = createUserWithEnvironmentStream(
      userId.trim(),
      selectedTemplate,
      (event: StreamEvent) => {
        // 실시간 로그 메시지 추가
        setLogs(prev => [...prev, event.message])
      },
      (data) => {
        // 완료 시
        setLogs(prev => [...prev, '✅ 모든 작업 완료!'])
        setGeneratedAccount({
          type: "user",
          code: data.access_code,
          userId: userId.trim(),
          environmentId: data.environment_id,
        })
        setIsCreating(false)
      },
      (error) => {
        // 에러 발생 시
        setCreateError(error)
        setIsCreating(false)
      }
    )

    closeStreamRef.current = closeStream
  }

  const handleLogout = () => {
    localStorage.removeItem("accessCode")
    localStorage.removeItem("userId")
    localStorage.removeItem("userType")
    localStorage.removeItem("environmentSet")
    router.push("/")
  }

  const handleAccountTypeChange = (type: "admin" | "user") => {
    if (type === "user" && !isEnvironmentSet) {
      alert("사용자 계정을 생성하려면 먼저 환경 설정에서 YAML 파일을 업로드해주세요.")
      return
    }
    setAccountType(type)
    setUserId("")
    setGeneratedAccount(null)
    setCreateError("")
  }

  if (!mounted) {
    return null
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" onClick={() => router.push("/admin")}>
              <svg className="w-5 h-5" fill="none" strokeWidth="2" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
              </svg>
            </Button>
            <h1 className="text-xl font-bold">계정 생성</h1>
          </div>
          <Button variant="ghost" onClick={handleLogout}>
            로그아웃
          </Button>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="max-w-3xl mx-auto space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>계정 타입 선택</CardTitle>
              <CardDescription>생성할 계정의 타입을 선택하세요</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => handleAccountTypeChange("admin")}
                  className={`p-6 border-2 rounded-lg transition-all ${
                    accountType === "admin" ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
                  }`}
                >
                  <div className="flex flex-col items-center gap-2">
                    <svg className="w-10 h-10" fill="none" strokeWidth="2" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"
                      />
                    </svg>
                    <p className="font-semibold">관계자</p>
                  </div>
                </button>
                <button
                  onClick={() => handleAccountTypeChange("user")}
                  className={`p-6 border-2 rounded-lg transition-all ${
                    accountType === "user"
                      ? "border-primary bg-primary/5"
                      : isEnvironmentSet
                        ? "border-border hover:border-primary/50"
                        : "border-border opacity-50 cursor-not-allowed"
                  }`}
                  disabled={!isEnvironmentSet}
                >
                  <div className="flex flex-col items-center gap-2">
                    <svg className="w-10 h-10" fill="none" strokeWidth="2" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z"
                      />
                    </svg>
                    <p className="font-semibold">사용자</p>
                    {!isEnvironmentSet && <p className="text-xs text-muted-foreground mt-1">환경 설정 필요</p>}
                  </div>
                </button>
              </div>
            </CardContent>
          </Card>

          {createError && (
            <div className="flex items-center gap-2 p-3 bg-destructive/10 text-destructive rounded-lg">
              <svg className="w-5 h-5" fill="none" strokeWidth="2" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
                />
              </svg>
              <span className="text-sm">{createError}</span>
            </div>
          )}

          {accountType === "admin" && !generatedAccount && (
            <Card>
              <CardHeader>
                <CardTitle>관계자 계정 생성</CardTitle>
                <CardDescription>새로운 관계자 계정을 생성합니다</CardDescription>
              </CardHeader>
              <CardContent>
                <Button className="w-full" size="lg" onClick={handleCreateAdminAccount} disabled={isCreating}>
                  {isCreating ? "생성 중..." : "계정 생성하기"}
                </Button>
              </CardContent>
            </Card>
          )}

          {accountType === "user" && !generatedAccount && (
            <Card>
              <CardHeader>
                <CardTitle>사용자 정보 설정</CardTitle>
                <CardDescription>사용자 이름과 템플릿을 선택하세요</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-2">
                  <label htmlFor="userId" className="text-sm font-medium">
                    사용자 이름
                  </label>
                  <Input
                    id="userId"
                    placeholder="사용자 이름 입력 (예: 테스트학생1)"
                    value={userId}
                    onChange={(e) => setUserId(e.target.value)}
                    disabled={isCreating}
                  />
                </div>

                <div className="space-y-2">
                  <label htmlFor="template" className="text-sm font-medium">
                    개발 환경 템플릿
                  </label>
                  <select
                    id="template"
                    value={selectedTemplate}
                    onChange={(e) => setSelectedTemplate(Number(e.target.value))}
                    disabled={isCreating}
                    className="w-full h-10 px-3 py-2 text-sm bg-background border border-input rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
                  >
                    <option value={1}>Node.js 개발 환경</option>
                    <option value={2}>Python ML 환경</option>
                    <option value={3}>Bash 간단 환경</option>
                  </select>
                  <p className="text-xs text-muted-foreground">
                    선택한 템플릿으로 개발 환경이 자동 생성됩니다
                  </p>
                </div>

                <Button className="w-full" size="lg" onClick={handleCreateUserAccount} disabled={isCreating}>
                  {isCreating ? "생성 중..." : "사용자 계정 + 환경 생성하기"}
                </Button>
              </CardContent>
            </Card>
          )}

          {showLogs && logs.length > 0 && (
            <Card className="border-blue-500">
              <CardHeader>
                <CardTitle className="text-blue-600">실시간 생성 로그</CardTitle>
                <CardDescription>환경 생성 과정을 실시간으로 확인하세요</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="bg-black/90 text-green-400 p-4 rounded-lg font-mono text-sm max-h-96 overflow-y-auto space-y-1">
                  {logs.map((log, index) => (
                    <div key={index} className="flex items-start gap-2">
                      <span className="text-gray-500">[{new Date().toLocaleTimeString()}]</span>
                      <span>{log}</span>
                    </div>
                  ))}
                  {isCreating && (
                    <div className="flex items-center gap-2 mt-2">
                      <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                      <span className="text-gray-400">처리 중...</span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {generatedAccount && (
            <Card className="border-primary">
              <CardHeader>
                <CardTitle className="text-primary">계정 생성 완료</CardTitle>
                <CardDescription>
                  {generatedAccount.type === "admin" ? "관계자" : "사용자"} 계정이 생성되었습니다
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {generatedAccount.type === "user" && (
                    <div className="space-y-3 mb-4 p-4 bg-secondary/50 rounded-lg">
                      <div>
                        <p className="text-sm text-muted-foreground mb-1">사용자 이름</p>
                        <p className="text-lg font-semibold">{generatedAccount.userId}</p>
                      </div>
                      {generatedAccount.environmentId && (
                        <div>
                          <p className="text-sm text-muted-foreground mb-1">개발 환경</p>
                          <div className="flex items-center gap-2">
                            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                            <p className="text-sm font-medium">환경 ID #{generatedAccount.environmentId} 생성 중</p>
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">
                            선택한 템플릿으로 Kubernetes 환경이 자동으로 프로비저닝됩니다
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="bg-primary/5 p-6 rounded-lg border border-primary/20">
                    <p className="text-sm text-muted-foreground mb-2">생성된 접속 코드</p>
                    <p className="text-3xl font-mono font-bold text-primary tracking-wider">{generatedAccount.code}</p>
                  </div>
                  <Button
                    className="w-full bg-transparent"
                    variant="outline"
                    onClick={() => router.push("/admin/monitor")}
                  >
                    모니터링으로 가기
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </main>
    </div>
  )
}
