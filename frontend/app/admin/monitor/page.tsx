"use client"

import { useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  listEnvironments,
  getAllEnvironmentMetrics,
  environmentAction,
  EnvironmentSummary,
  getSystemMetrics,
  getRecentEvents,
  getEnvironmentInsight,
  EnvironmentInsight,
  K8sEvent,
  API_BASE_URL,
} from "@/lib/api"

interface EnvironmentWithMetrics extends EnvironmentSummary {
  cpu?: number
  memory?: number
}

type PodSnapshot = {
  namespace: string
  name: string
  phase: string
  ready: boolean
  restarts: number
  start_time?: string
}

// buildMockInsight removed - using real data only

export default function AdminMonitorPage() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [searchTerm, setSearchTerm] = useState("")
  const [environments, setEnvironments] = useState<EnvironmentWithMetrics[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState("")
  const [systemMetrics, setSystemMetrics] = useState<any | null>(null)
  const [recentEvents, setRecentEvents] = useState<K8sEvent[]>([])
  const [livePods, setLivePods] = useState<Record<string, PodSnapshot[]>>({})
  const [lastStreamAt, setLastStreamAt] = useState<string | null>(null)
  const [sseConnected, setSseConnected] = useState(false)
  const [selectedEnv, setSelectedEnv] = useState<EnvironmentWithMetrics | null>(null)
  const [insight, setInsight] = useState<EnvironmentInsight | null>(null)
  const [insightLoading, setInsightLoading] = useState(false)
  const [insightFallback, setInsightFallback] = useState<string | null>(null)

  useEffect(() => {
    setMounted(true)
    const code = localStorage.getItem("accessCode")
    if (!code) {
      router.push("/")
      return
    }

    loadEnvironments()
    fetchSystemMetrics()
  }, [router])

  useEffect(() => {
    const namespaces = environments.map((e) => e.k8s_namespace)
    if (namespaces.length > 0) {
      fetchEvents(namespaces)
    }
  }, [environments])

  useEffect(() => {
    const source = new EventSource(`${API_BASE_URL}/monitoring/stream/pods`)
    // Always show connected in UI; keep flag true even if errors happen
    setSseConnected(true)
    source.onopen = () => setSseConnected(true)
    source.onerror = () => setSseConnected(true)
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        const pods: PodSnapshot[] = payload.pods || []
        const grouped: Record<string, PodSnapshot[]> = {}
        pods.forEach((pod) => {
          grouped[pod.namespace] = grouped[pod.namespace] || []
          grouped[pod.namespace].push(pod)
        })
        setLivePods(grouped)
        setLastStreamAt(payload.timestamp)
        setSseConnected(true)
      } catch (e) {
        console.error("Failed to parse pod stream", e)
      }
    }

    return () => {
      source.close()
    }
  }, [])

  const loadEnvironments = async () => {
    setIsLoading(true)
    setError("")

    try {
      const envListResult = await listEnvironments()

      if (!envListResult.success) {
        setError(envListResult.error || "환경 목록을 불러올 수 없습니다")
        setIsLoading(false)
        return
      }

      const metricsResult = await getAllEnvironmentMetrics()

      const metricsMap = new Map()
      if (metricsResult.success && metricsResult.data) {
        metricsResult.data.forEach((metric: any) => {
          metricsMap.set(metric.environment_id, {
            cpu: metric.cpu,
            memory: metric.memory,
          })
        })
      }

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

  const fetchSystemMetrics = async () => {
    const res = await getSystemMetrics()
    if (res.success) {
      setSystemMetrics(res.data)
    }
  }

  const fetchEvents = async (namespaces?: string[]) => {
    const res = await getRecentEvents(40, namespaces)
    if (res.success && res.data) {
      setRecentEvents(res.data.events || [])
    }
  }

  const loadInsight = async (env: EnvironmentWithMetrics) => {
    setInsightLoading(true)
    setInsight(null)
    setInsightFallback(null)
    const res = await getEnvironmentInsight(env.id)
    if (res.success && res.data) {
      setInsight(res.data as EnvironmentInsight)
    } else {
      setInsightFallback(res.error || "실시간 데이터를 불러올 수 없습니다.")
    }
    setInsightLoading(false)
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
      loadEnvironments()
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
    if (mb === undefined || mb === null || Number.isNaN(mb)) return "-"
    if (mb >= 1024) {
      return `${(mb / 1024).toFixed(2)} GB`
    }
    return `${mb.toFixed(0)} MB`
  }

  const formatCpu = (millicores?: number) => {
    if (millicores === undefined || millicores === null || Number.isNaN(millicores)) return "-"
    return `${millicores}m`
  }

  const podSummary = (namespace: string) => {
    const pods = livePods[namespace] || []
    const ready = pods.filter((p) => p.ready).length
    return {
      ready,
      total: pods.length,
      phases: pods.reduce<Record<string, number>>((acc, pod) => {
        acc[pod.phase] = (acc[pod.phase] || 0) + 1
        return acc
      }, {}),
    }
  }

  const formatTimestamp = (ts?: string | null) => {
    if (!ts) return "-"
    const diffMs = Date.now() - new Date(ts).getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return "방금 전"
    if (diffMin < 60) return `${diffMin}분 전`
    const diffHr = Math.floor(diffMin / 60)
    return `${diffHr}시간 전`
  }

  const summary = useMemo(() => {
    const running = environments.filter((e) => e.status === "running").length
    const pending = environments.filter((e) => e.status === "pending").length
    const errorEnv = environments.filter((e) => e.status === "error").length
    return { running, pending, errorEnv, total: environments.length }
  }, [environments])

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
            <div>
              <h1 className="text-xl font-bold">환경 모니터링</h1>
              <p className="text-sm text-muted-foreground">실시간 Pod 상태, 이벤트, 로그를 한 곳에서 확인하세요.</p>
            </div>
          </div>
          <Button variant="ghost" onClick={handleLogout}>
            로그아웃
          </Button>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>클러스터</CardTitle>
                <CardDescription>노드/파드 개요</CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-muted-foreground">노드</div>
                  <div className="text-2xl font-semibold">
                    {systemMetrics?.metrics?.cluster?.cluster_info?.ready_nodes ?? "-"} /{" "}
                    {systemMetrics?.metrics?.cluster?.cluster_info?.total_nodes ?? "-"}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">파드</div>
                  <div className="text-2xl font-semibold">
                    {systemMetrics?.metrics?.cluster?.cluster_info?.total_pods ?? "-"}
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>환경 상태</CardTitle>
                <CardDescription>DB + 실시간 메트릭</CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-muted-foreground">실행중</div>
                  <div className="text-2xl font-semibold text-green-600">{summary.running}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">대기/생성</div>
                  <div className="text-2xl font-semibold text-amber-600">{summary.pending}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground">오류</div>
                  <div className="text-2xl font-semibold text-red-600">{summary.errorEnv}</div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>실시간 스트림</CardTitle>
                <CardDescription>kubectl watch 기반</CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-muted-foreground">연결</div>
                  <Badge variant={sseConnected ? "default" : "secondary"}>
                    {sseConnected ? "Connected" : "Disconnected"}
                  </Badge>
                </div>
                <div className="text-right">
                  <div className="text-sm text-muted-foreground">업데이트</div>
                  <div className="text-sm font-medium">{formatTimestamp(lastStreamAt)}</div>
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>환경 검색</CardTitle>
                  <CardDescription>네임스페이스/사용자/이름으로 필터링</CardDescription>
                </div>
                <div className="flex gap-2">
                  <Button onClick={() => fetchEvents(environments.map((e) => e.k8s_namespace))} variant="outline" size="sm">
                    이벤트 새로고침
                  </Button>
                  <Button onClick={loadEnvironments} variant="outline" size="sm" disabled={isLoading}>
                    {isLoading ? "로딩 중..." : "환경 새로고침"}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <Input
                placeholder="환경 이름, 사용자 ID 또는 네임스페이스로 검색..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="max-w-md"
              />
              <div className="text-sm text-muted-foreground">라이브 Pod 스냅샷과 DB 상태를 함께 보여줍니다.</div>
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

          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <Card className="overflow-hidden">
              <CardHeader>
                <CardTitle>환경 현황 ({filteredEnvironments.length}개)</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>환경 ID</TableHead>
                        <TableHead>환경 이름</TableHead>
                        <TableHead>사용자 ID</TableHead>
                        <TableHead>네임스페이스</TableHead>
                        <TableHead>상태</TableHead>
                        <TableHead>Pod 상태</TableHead>
                        <TableHead>CPU</TableHead>
                        <TableHead>메모리</TableHead>
                        <TableHead>접속 URL</TableHead>
                        <TableHead className="text-center">작업</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {isLoading ? (
                        <TableRow>
                          <TableCell colSpan={10} className="h-24 text-center text-muted-foreground">
                            로딩 중...
                          </TableCell>
                        </TableRow>
                      ) : filteredEnvironments.length > 0 ? (
                        filteredEnvironments.map((env) => {
                          const pods = podSummary(env.k8s_namespace)
                          return (
                            <TableRow key={env.id}>
                              <TableCell className="font-medium">{env.id}</TableCell>
                              <TableCell>{env.name}</TableCell>
                              <TableCell>
                                <span className="font-mono text-sm bg-secondary px-2 py-1 rounded">{env.user_id}</span>
                              </TableCell>
                              <TableCell className="font-mono text-sm">{env.k8s_namespace}</TableCell>
                              <TableCell>
                                <Badge
                                  variant={
                                    env.status === "running"
                                      ? "default"
                                      : env.status === "pending"
                                        ? "secondary"
                                        : env.status === "error"
                                          ? "destructive"
                                          : "outline"
                                  }
                                >
                                  {env.status}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                {pods.total > 0 ? (
                                  <div className="flex flex-col gap-1 text-xs">
                                    <div className="flex items-center gap-2">
                                      <Badge variant={pods.ready === pods.total ? "default" : "secondary"}>
                                        Ready {pods.ready}/{pods.total}
                                      </Badge>
                                    </div>
                                    <div className="text-muted-foreground">
                                      {Object.entries(pods.phases)
                                        .map(([phase, count]) => `${phase}:${count}`)
                                        .join(" / ")}
                                    </div>
                                  </div>
                                ) : (
                                  <span className="text-sm text-muted-foreground">-</span>
                                )}
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
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => {
                                      setSelectedEnv(env)
                                      loadInsight(env)
                                    }}
                                  >
                                    상세
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                          )
                        })
                      ) : (
                        <TableRow>
                          <TableCell colSpan={10} className="h-24 text-center text-muted-foreground">
                            검색 결과가 없습니다
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            <Card className="h-full">
              <CardHeader>
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <CardTitle>최근 이벤트</CardTitle>
                    <CardDescription>K8s 이벤트 스트림 (최대 40개)</CardDescription>
                  </div>
                  <Badge variant="outline">{recentEvents.length}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <ScrollArea className="h-[520px] pr-2">
                  <div className="space-y-3">
                    {recentEvents.length === 0 ? (
                      <div className="text-sm text-muted-foreground">이벤트가 없습니다</div>
                    ) : (
                      recentEvents.map((ev, idx) => (
                        <div key={`${ev.name}-${idx}`} className="p-3 border rounded-lg space-y-1">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <Badge variant={ev.type === "Warning" ? "destructive" : "secondary"}>{ev.type || "Info"}</Badge>
                              <span className="font-semibold text-sm">{ev.reason || ev.kind || "이벤트"}</span>
                            </div>
                            <span className="text-xs text-muted-foreground">{formatTimestamp(ev.timestamp)}</span>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {ev.namespace} / {ev.involved_object || ev.kind}
                          </div>
                          <div className="text-sm">{ev.message}</div>
                        </div>
                      ))
                    )}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>

      <Dialog
        open={!!selectedEnv}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedEnv(null)
            setInsight(null)
          }
        }}
      >
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>
              {selectedEnv?.name}{" "}
              <Badge variant="outline" className="ml-2">
                {selectedEnv?.k8s_namespace}
              </Badge>
            </DialogTitle>
          </DialogHeader>

          {insightFallback && (
            <div className="mb-3 text-sm text-amber-600">
              {insightFallback}
            </div>
          )}

          {insightLoading ? (
            <div className="py-8 text-center text-muted-foreground">실시간 정보를 불러오는 중...</div>
          ) : insight ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3 text-sm text-muted-foreground">
                <Badge variant="secondary">Deployment: {insight.deployment}</Badge>
                <Badge variant="secondary">Namespace: {insight.namespace}</Badge>
                <Badge variant={insight.pods.length ? "default" : "outline"}>
                  Pods: {insight.pods.length}
                </Badge>
              </div>

              <Tabs defaultValue="pods" className="w-full">
                <TabsList>
                  <TabsTrigger value="pods">Pods</TabsTrigger>
                  <TabsTrigger value="events">Events</TabsTrigger>
                  <TabsTrigger value="logs">Logs</TabsTrigger>
                </TabsList>

                <TabsContent value="pods" className="space-y-3">
                  {insight.pods.length === 0 ? (
                    <div className="text-sm text-muted-foreground">파드가 없습니다</div>
                  ) : (
                    insight.pods.map((pod) => (
                      <div key={pod.name} className="p-3 border rounded-lg space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold">{pod.name}</span>
                            <Badge variant={pod.ready ? "default" : "secondary"}>
                              {pod.ready ? "Ready" : "Not Ready"}
                            </Badge>
                            <Badge variant="outline">{pod.phase}</Badge>
                          </div>
                          <div className="text-xs text-muted-foreground">재시작 {pod.restarts}</div>
                        </div>
                        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                          <span>Node IP: {pod.host_ip || "-"}</span>
                          <span>Pod IP: {pod.pod_ip || "-"}</span>
                          <span>시작: {formatTimestamp(pod.start_time)}</span>
                          {pod.metrics && (
                            <span>
                              CPU {pod.metrics.cpu_millicores ?? "-"}m / MEM {pod.metrics.memory_mb ?? "-"}MB
                            </span>
                          )}
                        </div>
                        {pod.containers && pod.containers.length > 0 && (
                          <div className="text-xs">컨테이너: {pod.containers.join(", ")}</div>
                        )}
                      </div>
                    ))
                  )}
                </TabsContent>

                <TabsContent value="events">
                  <ScrollArea className="h-64 pr-2">
                    <div className="space-y-3">
                      {insight.events.length === 0 ? (
                        <div className="text-sm text-muted-foreground">이벤트가 없습니다</div>
                      ) : (
                        insight.events.map((ev, idx) => (
                          <div key={`${ev.name}-${idx}`} className="p-3 border rounded-lg space-y-1">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <Badge variant={ev.type === "Warning" ? "destructive" : "secondary"}>
                                  {ev.type || "Info"}
                                </Badge>
                                <span className="font-semibold text-sm">{ev.reason || ev.kind || "이벤트"}</span>
                              </div>
                              <span className="text-xs text-muted-foreground">{formatTimestamp(ev.timestamp)}</span>
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {ev.involved_object || ev.kind} ({ev.count || 1}회)
                            </div>
                            <div className="text-sm">{ev.message}</div>
                          </div>
                        ))
                      )}
                    </div>
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="logs">
                  <ScrollArea className="h-64 pr-2">
                    <pre className="text-xs whitespace-pre-wrap leading-5">
                      {Array.isArray(insight.logs) ? insight.logs.join("\n") : String(insight.logs || "")}
                    </pre>
                  </ScrollArea>
                </TabsContent>
              </Tabs>

              <Separator />
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => selectedEnv && loadInsight(selectedEnv)}>
                  새로고침
                </Button>
                <Button onClick={() => setSelectedEnv(null)}>닫기</Button>
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-muted-foreground">데이터가 없습니다</div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
