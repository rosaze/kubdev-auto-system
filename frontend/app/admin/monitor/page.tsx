"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { getUserList, getMetrics, stopPod, restartPod, deletePod } from "@/lib/api"

interface UserAccount {
  id: string
  code: string
  nodeName?: string
  ip?: string
  port?: number
  cpuUsage?: number
  permissions: string[]
}

export default function AdminMonitorPage() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [searchTerm, setSearchTerm] = useState("")
  const [accounts, setAccounts] = useState<UserAccount[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    setMounted(true)
    const code = localStorage.getItem("accessCode")
    if (!code) {
      router.push("/")
      return
    }

    loadUserAccounts()
  }, [router])

  const loadUserAccounts = async () => {
    const currentUserId = localStorage.getItem("userId")
    if (!currentUserId) {
      setError("사용자 정보를 찾을 수 없습니다. 다시 로그인해주세요.")
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    setError("")

    // 사용자 목록 가져오기
    const userListResult = await getUserList(currentUserId)

    if (!userListResult.success) {
      setError(userListResult.error || "계정 목록을 불러올 수 없습니다")
      setIsLoading(false)
      return
    }

    // 각 사용자의 메트릭 정보 가져오기
    const usersWithMetrics: UserAccount[] = []

    for (const user of userListResult.data || []) {
      const metricsResult = await getMetrics(user.user_id)

      if (metricsResult.success && metricsResult.data) {
        usersWithMetrics.push({
          id: user.user_id,
          code: user.user_code,
          nodeName: metricsResult.data.node_name,
          ip: metricsResult.data.ip,
          port: metricsResult.data.port,
          cpuUsage: metricsResult.data.cpu_usage,
          permissions: ["read", "write"], // 권한 정보는 추후 API에서 제공될 예정
        })
      } else {
        // 메트릭을 불러오지 못한 경우에도 기본 정보는 표시
        usersWithMetrics.push({
          id: user.user_id,
          code: user.user_code,
          permissions: ["read", "write"],
        })
      }
    }

    setAccounts(usersWithMetrics)
    setIsLoading(false)
  }

  const handleStopPod = async (targetUserId: string) => {
    const currentUserId = localStorage.getItem("userId")
    if (!currentUserId) return

    const result = await stopPod(currentUserId, targetUserId)

    if (result.success) {
      alert("Pod가 중지되었습니다.")
      loadUserAccounts() // 데이터 새로고침
    } else {
      alert(result.error || "Pod 중지에 실패했습니다")
    }
  }

  const handleRestartPod = async (targetUserId: string) => {
    const currentUserId = localStorage.getItem("userId")
    if (!currentUserId) return

    const result = await restartPod(currentUserId, targetUserId)

    if (result.success) {
      alert("Pod가 재시작되었습니다.")
      loadUserAccounts() // 데이터 새로고침
    } else {
      alert(result.error || "Pod 재시작에 실패했습니다")
    }
  }

  const handleDeletePod = async (targetUserId: string) => {
    if (!confirm("정말로 이 Pod를 삭제하시겠습니까?")) return

    const currentUserId = localStorage.getItem("userId")
    if (!currentUserId) return

    const result = await deletePod(currentUserId, targetUserId)

    if (result.success) {
      alert("Pod가 삭제되었습니다.")
      loadUserAccounts() // 데이터 새로고침
    } else {
      alert(result.error || "Pod 삭제에 실패했습니다")
    }
  }

  const handleLogout = () => {
    localStorage.removeItem("accessCode")
    localStorage.removeItem("userId")
    localStorage.removeItem("userType")
    router.push("/")
  }

  const filteredAccounts = accounts.filter(
    (account) =>
      account.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      account.code.toLowerCase().includes(searchTerm.toLowerCase()),
  )

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
            <h1 className="text-xl font-bold">계정 모니터링</h1>
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
                <CardTitle>사용자 계정 검색</CardTitle>
                <Button onClick={loadUserAccounts} variant="outline" size="sm" disabled={isLoading}>
                  {isLoading ? "로딩 중..." : "새로고침"}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <Input
                placeholder="ID 또는 코드로 검색..."
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
              <CardTitle>사용자 계정 현황 ({filteredAccounts.length}개)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>코드</TableHead>
                      <TableHead>노드 이름</TableHead>
                      <TableHead>IP</TableHead>
                      <TableHead>포트</TableHead>
                      <TableHead>CPU 사용률</TableHead>
                      <TableHead>권한</TableHead>
                      <TableHead className="text-center">작업</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {isLoading ? (
                      <TableRow>
                        <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                          로딩 중...
                        </TableCell>
                      </TableRow>
                    ) : filteredAccounts.length > 0 ? (
                      filteredAccounts.map((account, index) => (
                        <TableRow key={index}>
                          <TableCell className="font-medium">{account.id}</TableCell>
                          <TableCell>
                            <span className="font-mono text-sm bg-secondary px-2 py-1 rounded">{account.code}</span>
                          </TableCell>
                          <TableCell>{account.nodeName || "-"}</TableCell>
                          <TableCell className="font-mono text-sm">{account.ip || "-"}</TableCell>
                          <TableCell>{account.port || "-"}</TableCell>
                          <TableCell>
                            {account.cpuUsage !== undefined ? (
                              <div className="flex items-center gap-2">
                                <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden max-w-[60px]">
                                  <div
                                    className={`h-full rounded-full ${
                                      account.cpuUsage > 70
                                        ? "bg-red-500"
                                        : account.cpuUsage > 50
                                          ? "bg-yellow-500"
                                          : "bg-accent"
                                    }`}
                                    style={{ width: `${account.cpuUsage}%` }}
                                  />
                                </div>
                                <span className="text-sm font-medium">{account.cpuUsage}%</span>
                              </div>
                            ) : (
                              "-"
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="flex flex-wrap gap-1">
                              {account.permissions.map((permission) => (
                                <span
                                  key={permission}
                                  className="inline-flex items-center px-2 py-0.5 bg-primary/10 text-primary rounded text-xs font-medium"
                                >
                                  {permission === "read" ? "읽기" : "쓰기"}
                                </span>
                              ))}
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center justify-center gap-1">
                              <Button variant="ghost" size="sm" onClick={() => handleStopPod(account.id)} title="중지">
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
                                onClick={() => handleRestartPod(account.id)}
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
                                onClick={() => handleDeletePod(account.id)}
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
                        <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
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
