"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

const DUMMY_USER_ACCOUNTS = [
  {
    id: "user001",
    code: "ABCDE",
    nodeName: "node-worker-01",
    ip: "192.168.1.101",
    port: 8080,
    cpuUsage: 45.2,
    permissions: ["read", "write"],
  },
  {
    id: "user002",
    code: "FGHIJ",
    nodeName: "node-worker-02",
    ip: "192.168.1.102",
    port: 8081,
    cpuUsage: 62.8,
    permissions: ["read"],
  },
  {
    id: "user003",
    code: "KLMNO",
    nodeName: "node-worker-01",
    ip: "192.168.1.103",
    port: 8082,
    cpuUsage: 28.5,
    permissions: ["write"],
  },
  {
    id: "dev-team",
    code: "PQRST",
    nodeName: "node-worker-03",
    ip: "192.168.1.104",
    port: 8083,
    cpuUsage: 73.1,
    permissions: ["read", "write"],
  },
]

export default function AdminMonitorPage() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [searchTerm, setSearchTerm] = useState("")
  const [accounts] = useState(DUMMY_USER_ACCOUNTS)

  useEffect(() => {
    setMounted(true)
    const code = localStorage.getItem("accessCode")
    if (!code) {
      router.push("/")
    }
  }, [router])

  const handleLogout = () => {
    localStorage.removeItem("accessCode")
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
              <CardTitle>사용자 계정 검색</CardTitle>
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
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredAccounts.length > 0 ? (
                      filteredAccounts.map((account, index) => (
                        <TableRow key={index}>
                          <TableCell className="font-medium">{account.id}</TableCell>
                          <TableCell>
                            <span className="font-mono text-sm bg-secondary px-2 py-1 rounded">{account.code}</span>
                          </TableCell>
                          <TableCell>{account.nodeName}</TableCell>
                          <TableCell className="font-mono text-sm">{account.ip}</TableCell>
                          <TableCell>{account.port}</TableCell>
                          <TableCell>
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
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
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
