"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getMetrics } from "@/lib/api"

interface Tool {
  name: string
  version: string
  status: string
}

export default function UserHomePage() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [tools, setTools] = useState<Tool[]>([])
  const [metrics, setMetrics] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    setMounted(true)
    const code = localStorage.getItem("accessCode")
    if (!code) {
      router.push("/")
      return
    }

    loadMetrics()
  }, [router])

  const loadMetrics = async () => {
    const userId = localStorage.getItem("userId")
    if (!userId) {
      setError("사용자 정보를 찾을 수 없습니다. 다시 로그인해주세요.")
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    setError("")

    const result = await getMetrics(userId)

    if (result.success && result.data) {
      setMetrics(result.data)
      // 더미 도구 목록 설정 (실제로는 API에서 제공될 수 있음)
      setTools([
        { name: "VS Code", version: "1.85.0", status: "installed" },
        { name: "Python", version: "3.11.5", status: "installed" },
        { name: "Docker", version: "24.0.7", status: "installed" },
      ])
    } else {
      setError(result.error || "메트릭 정보를 불러올 수 없습니다")
    }

    setIsLoading(false)
  }

  const handleLogout = () => {
    localStorage.removeItem("accessCode")
    localStorage.removeItem("userId")
    localStorage.removeItem("userType")
    router.push("/")
  }

  if (!mounted) {
    return null
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-accent/20 rounded-lg flex items-center justify-center">
              <svg
                className="w-6 h-6 text-accent"
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
            <h1 className="text-xl font-bold">사용자 홈</h1>
          </div>
          <Button variant="ghost" onClick={handleLogout}>
            로그아웃
          </Button>
        </div>
      </header>

      <main className="container mx-auto px-4 py-12">
        <div className="max-w-4xl mx-auto space-y-8">
          <div className="text-center space-y-3">
            <h2 className="text-4xl font-bold text-balance">환영합니다</h2>
            <p className="text-lg text-muted-foreground">할당된 도구를 확인하고 사용을 시작하세요</p>
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 bg-destructive/10 text-destructive rounded-lg">
              <svg className="w-5 h-5" fill="none" strokeWidth="2" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
                />
              </svg>
              <span className="text-sm">{error}</span>
            </div>
          )}

          <Card className="bg-gradient-to-br from-blue-50/50 to-indigo-50/50 border-blue-200/50 dark:from-blue-950/20 dark:to-indigo-950/20 dark:border-blue-800/30">
            <CardHeader>
              <CardTitle className="text-2xl flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-500 text-white rounded-lg flex items-center justify-center">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
                    />
                  </svg>
                </div>
                웹 IDE 접속
              </CardTitle>
              <CardDescription className="text-base">할당된 VS Code 환경에 접속하여 개발을 시작하세요</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* 환경 상태 표시 */}
              <div className="flex items-center gap-3 p-3 bg-white/50 dark:bg-gray-800/50 rounded-lg border">
                <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                <div>
                  <p className="font-medium text-sm">환경 상태</p>
                  <p className="text-xs text-muted-foreground">실행 중 - 접속 가능</p>
                </div>
              </div>

              {/* Git 리포지토리 정보 (향후 백엔드에서 가져올 예정) */}
              <div className="flex items-center gap-3 p-3 bg-white/50 dark:bg-gray-800/50 rounded-lg border">
                <svg className="w-5 h-5 text-gray-600" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
                <div className="flex-1">
                  <p className="font-medium text-sm">연결된 프로젝트</p>
                  <p className="text-xs text-muted-foreground">설정된 Git 리포지토리가 자동으로 로드됩니다</p>
                </div>
              </div>

              {/* VS Code 접속 버튼 */}
              <Button
                className="w-full h-14 text-lg font-semibold bg-blue-600 hover:bg-blue-700 text-white"
                onClick={() => {
                  // 향후 백엔드 API로 접속 URL 가져올 예정
                  const accessUrl = `http://user-env-${localStorage.getItem("accessCode")?.toLowerCase()}.kubdev.local`
                  window.open(accessUrl, "_blank")
                }}
              >
                <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                  />
                </svg>
                VS Code 환경 접속
              </Button>

              <p className="text-xs text-muted-foreground text-center">새 탭에서 웹 기반 VS Code가 실행됩니다</p>
            </CardContent>
          </Card>

          {metrics && (
            <Card>
              <CardHeader>
                <CardTitle className="text-2xl">리소스 정보</CardTitle>
                <CardDescription className="text-base">현재 할당된 리소스 정보입니다</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid md:grid-cols-2 gap-4">
                  <div className="p-4 bg-secondary/50 rounded-lg">
                    <p className="text-sm text-muted-foreground mb-1">노드 이름</p>
                    <p className="text-lg font-semibold">{metrics.node_name || "-"}</p>
                  </div>
                  <div className="p-4 bg-secondary/50 rounded-lg">
                    <p className="text-sm text-muted-foreground mb-1">IP 주소</p>
                    <p className="text-lg font-semibold font-mono">{metrics.ip || "-"}</p>
                  </div>
                  <div className="p-4 bg-secondary/50 rounded-lg">
                    <p className="text-sm text-muted-foreground mb-1">포트</p>
                    <p className="text-lg font-semibold">{metrics.port || "-"}</p>
                  </div>
                  <div className="p-4 bg-secondary/50 rounded-lg">
                    <p className="text-sm text-muted-foreground mb-1">CPU 사용률</p>
                    <div className="flex items-center gap-2 mt-1">
                      <div className="flex-1 h-3 bg-secondary rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            metrics.cpu_usage > 70
                              ? "bg-red-500"
                              : metrics.cpu_usage > 50
                                ? "bg-yellow-500"
                                : "bg-accent"
                          }`}
                          style={{ width: `${metrics.cpu_usage || 0}%` }}
                        />
                      </div>
                      <span className="text-lg font-semibold">{metrics.cpu_usage || 0}%</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-2xl">사용 가능한 도구</CardTitle>
              <CardDescription className="text-base">귀하의 계정에 설치된 개발 도구 목록입니다</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="text-center py-8 text-muted-foreground">로딩 중...</div>
              ) : (
                <div className="grid md:grid-cols-2 gap-4">
                  {tools.map((tool, index) => (
                    <div
                      key={index}
                      className="flex items-center gap-4 p-4 bg-secondary/50 rounded-lg hover:bg-secondary transition-colors"
                    >
                      <div className="w-12 h-12 bg-accent/10 rounded-lg flex items-center justify-center flex-shrink-0">
                        <svg
                          className="w-6 h-6 text-accent"
                          fill="none"
                          strokeWidth="2"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"
                          />
                        </svg>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-lg">{tool.name}</p>
                        <p className="text-sm text-muted-foreground">버전 {tool.version}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <svg
                          className="w-5 h-5 text-accent"
                          fill="none"
                          strokeWidth="2"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                          />
                        </svg>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-primary/5 to-accent/5 border-primary/20">
            <CardHeader>
              <CardTitle className="text-2xl">시작 가이드</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-start gap-3">
                <div className="w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 mt-0.5">
                  1
                </div>
                <div>
                  <p className="font-medium">개발 환경 확인</p>
                  <p className="text-sm text-muted-foreground">
                    위에 나열된 도구들이 정상적으로 설치되었는지 확인하세요
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 mt-0.5">
                  2
                </div>
                <div>
                  <p className="font-medium">프로젝트 시작</p>
                  <p className="text-sm text-muted-foreground">필요한 도구를 사용하여 개발을 시작하세요</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 mt-0.5">
                  3
                </div>
                <div>
                  <p className="font-medium">지원 요청</p>
                  <p className="text-sm text-muted-foreground">문제가 발생하면 관계자에게 문의하세요</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  )
}
