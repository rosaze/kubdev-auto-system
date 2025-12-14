"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { listEnvironments, getAllEnvironmentMetrics, environmentAction, EnvironmentSummary } from "@/lib/api"

interface EnvironmentWithMetrics extends EnvironmentSummary {
  cpu?: number
  memory?: number
}

export default function AdminMonitorPage() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [searchTerm, setSearchTerm] = useState("")
  const [environments, setEnvironments] = useState<EnvironmentWithMetrics[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    setMounted(true)
    const code = localStorage.getItem("accessCode")
    if (!code) {
      router.push("/")
      return
    }

    loadEnvironments()
  }, [router])

  const loadEnvironments = async () => {
    setIsLoading(true)
    setError("")

    try {
      // 모든 환경 목록 가져오기
      const envListResult = await listEnvironments()

      if (!envListResult.success) {
        setError(envListResult.error || "환경 목록을 불러올 수 없습니다")
        setIsLoading(false)
        return
      }

      // 메트릭 정보 가져오기
      const metricsResult = await getAllEnvironmentMetrics()

      // 메트릭 데이터를 환경 ID로 매핑
      const metricsMap = new Map()
      if (metricsResult.success && metricsResult.data) {
        metricsResult.data.forEach((metric: any) => {
          metricsMap.set(metric.environment_id, {
            cpu: metric.cpu,
            memory: metric.memory,
          })
        })
      }

      // 환경 목록에 메트릭 데이터 추가
      const envsWithMetrics: EnvironmentWithMetrics[] = (envListResult.data || []).map((env) => {
        const metrics = metricsMap.get(env.id)
        return {
          ...env,
          cpu: metrics?.cpu,
          memory: metrics?.memory,
        }
      })

      setEnvironments(envsWithMetrics)
    } catch (err) {
      setError("환경 정보를 불러오는 중 오류가 발생했습니다")
    } finally {
      setIsLoading(false)
    }
  }

  const handleAction = async (environmentId: number, action: "stop" | "restart" | "delete", envName: string) => {
    const confirmMessages = {
      stop: "정말로 이 환경을 중지하시겠습니까?",
      restart: "정말로 이 환경을 재시작하시겠습니까?",
      delete: "정말로 이 환경을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.",
    }

    if (!confirm(`${envName}: ${confirmMessages[action]}`)) return

    const result = await environmentAction(environmentId, action)

    if (result.success) {
      alert(`환경이 ${action === "stop" ? "중지" : action === "restart" ? "재시작" : "삭제"}되었습니다.`)
      loadEnvironments() // 데이터 새로고침
    } else {
      alert(result.error || `환경 ${action} 작업에 실패했습니다`)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem("accessCode")
    localStorage.removeItem("userId")
    localStorage.removeItem("userType")
    router.push("/")
  }

  const filteredEnvironments = environments.filter(
    (env) =>
      env.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      env.user_id.toString().includes(searchTerm) ||
      env.k8s_namespace.toLowerCase().includes(searchTerm.toLowerCase()),
  )

  const formatMemory = (mb?: number) => {
    if (!mb) return "-"
    if (mb >= 1024) {
      return `${(mb / 1024).toFixed(2)} GB`
    }
    return `${mb.toFixed(0)} MB`
  }

  const formatCpu = (millicores?: number) => {
    if (!millicores) return "-"
    return `${millicores}m`
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
            <h1 className="text-xl font-bold">환경 모니터링</h1>
          </div>
          <Button variant="ghost" onClick={handleLogout}>
            로그아웃
          </Button>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>환경 검색</CardTitle>
                <Button onClick={loadEnvironments} variant="outline" size="sm" disabled={isLoading}>
                  {isLoading ? "로딩 중..." : "새로고침"}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <Input
                placeholder="환경 이름, 사용자 ID 또는 네임스페이스로 검색..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="max-w-md"
              />
            </CardContent>
          </Card>

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

          <Card>
            <CardHeader>
              <CardTitle>환경 현황 ({filteredEnvironments.length}개)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>환경 ID</TableHead>
                      <TableHead>환경 이름</TableHead>
                      <TableHead>사용자 ID</TableHead>
                      <TableHead>네임스페이스</TableHead>
                      <TableHead>상태</TableHead>
                      <TableHead>CPU</TableHead>
                      <TableHead>메모리</TableHead>
                      <TableHead>접속 URL</TableHead>
                      <TableHead className="text-center">작업</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {isLoading ? (
                      <TableRow>
                        <TableCell colSpan={9} className="h-24 text-center text-muted-foreground">
                          로딩 중...
                        </TableCell>
                      </TableRow>
                    ) : filteredEnvironments.length > 0 ? (
                      filteredEnvironments.map((env) => (
                        <TableRow key={env.id}>
                          <TableCell className="font-medium">{env.id}</TableCell>
                          <TableCell>{env.name}</TableCell>
                          <TableCell>
                            <span className="font-mono text-sm bg-secondary px-2 py-1 rounded">{env.user_id}</span>
                          </TableCell>
                          <TableCell className="font-mono text-sm">{env.k8s_namespace}</TableCell>
                          <TableCell>
                            <span
                              className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                                env.status === "running"
                                  ? "bg-green-100 text-green-800"
                                  : env.status === "pending"
                                    ? "bg-yellow-100 text-yellow-800"
                                    : env.status === "error"
                                      ? "bg-red-100 text-red-800"
                                      : "bg-gray-100 text-gray-800"
                              }`}
                            >
                              {env.status}
                            </span>
                          </TableCell>
                          <TableCell className="font-mono text-sm">{formatCpu(env.cpu)}</TableCell>
                          <TableCell className="font-mono text-sm">{formatMemory(env.memory)}</TableCell>
                          <TableCell>
                            {env.access_url ? (
                              <a
                                href={env.access_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-primary hover:underline text-sm"
                              >
                                접속
                              </a>
                            ) : (
                              <span className="text-muted-foreground text-sm">-</span>
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center justify-center gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleAction(env.id, "stop", env.name)}
                                title="중지"
                              >
                                <svg
                                  className="w-4 h-4"
                                  fill="none"
                                  strokeWidth="2"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M5.25 7.5A2.25 2.25 0 017.5 5.25h9a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25h-9a2.25 2.25 0 01-2.25-2.25v-9z"
                                  />
                                </svg>
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleAction(env.id, "restart", env.name)}
                                title="재시작"
                              >
                                <svg
                                  className="w-4 h-4"
                                  fill="none"
                                  strokeWidth="2"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99"
                                  />
                                </svg>
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleAction(env.id, "delete", env.name)}
                                title="삭제"
                                className="text-destructive hover:text-destructive"
                              >
                                <svg
                                  className="w-4 h-4"
                                  fill="none"
                                  strokeWidth="2"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"
                                  />
                                </svg>
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={9} className="h-24 text-center text-muted-foreground">
                          검색 결과가 없습니다
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  )
}
