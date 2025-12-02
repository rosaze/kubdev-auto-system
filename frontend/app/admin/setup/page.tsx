"use client"

import type React from "react"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { uploadYaml } from "@/lib/api"

const DUMMY_TOOLS = [
  { name: "VS Code", version: "1.85.0", status: "active" },
  { name: "nginx", version: "1.24.0", status: "active" },
  { name: "Python", version: "3.11.5", status: "active" },
  { name: "Docker", version: "24.0.7", status: "active" },
  { name: "Git", version: "2.42.0", status: "active" },
]

export default function AdminSetupPage() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [environmentFile, setEnvironmentFile] = useState<File | null>(null)
  const [isEnvironmentSet, setIsEnvironmentSet] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState("")

  useEffect(() => {
    setMounted(true)
    const code = localStorage.getItem("accessCode")
    if (!code) {
      router.push("/")
      return
    }

    // 기존에 환경이 설정되어 있는지 확인
    const savedEnvironment = localStorage.getItem("environmentSet")
    if (savedEnvironment === "true") {
      setIsEnvironmentSet(true)
    }
  }, [router])

  const handleEnvironmentFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0]
      setEnvironmentFile(file)
      setIsUploading(true)
      setUploadError("")

      const userId = localStorage.getItem("userId")
      if (!userId) {
        setUploadError("사용자 정보를 찾을 수 없습니다. 다시 로그인해주세요.")
        setIsUploading(false)
        return
      }

      const result = await uploadYaml(userId, file)

      if (result.success) {
        setIsEnvironmentSet(true)
        localStorage.setItem("environmentSet", "true")
      } else {
        setUploadError(result.error || "업로드에 실패했습니다")
        setEnvironmentFile(null)
      }

      setIsUploading(false)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem("accessCode")
    localStorage.removeItem("userId")
    localStorage.removeItem("userType")
    localStorage.removeItem("environmentSet")
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
            <Button variant="ghost" size="icon" onClick={() => router.push("/admin")}>
              <svg className="w-5 h-5" fill="none" strokeWidth="2" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
              </svg>
            </Button>
            <h1 className="text-xl font-bold">환경 설정</h1>
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
              <CardTitle>환경 설정</CardTitle>
              <CardDescription>사용자 계정 생성을 위한 환경을 설정합니다</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="border-2 border-dashed border-border rounded-lg p-8 text-center hover:border-primary transition-colors">
                <input
                  type="file"
                  accept=".yaml,.yml"
                  onChange={handleEnvironmentFileChange}
                  className="hidden"
                  id="environment-file-upload"
                  disabled={isUploading}
                />
                <label htmlFor="environment-file-upload" className={isUploading ? "cursor-wait" : "cursor-pointer"}>
                  <div className="flex flex-col items-center gap-2">
                    <svg
                      className="w-12 h-12 text-muted-foreground"
                      fill="none"
                      strokeWidth="2"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z"
                      />
                    </svg>
                    <div>
                      <p className="font-medium">{isUploading ? "업로드 중..." : "클릭하여 YAML 파일 선택"}</p>
                      <p className="text-sm text-muted-foreground">.yaml 또는 .yml 파일</p>
                    </div>
                  </div>
                </label>
              </div>

              {uploadError && (
                <div className="flex items-center gap-2 p-3 bg-destructive/10 text-destructive rounded-lg">
                  <svg className="w-5 h-5" fill="none" strokeWidth="2" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
                    />
                  </svg>
                  <span className="text-sm">{uploadError}</span>
                </div>
              )}

              {environmentFile && !uploadError && (
                <div className="flex items-center gap-2 p-3 bg-secondary rounded-lg">
                  <svg
                    className="w-5 h-5 text-primary"
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
                  <span className="font-medium">{environmentFile.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">환경 설정 완료</span>
                </div>
              )}

              {isEnvironmentSet && (
                <div className="space-y-3 mt-4 pt-4 border-t">
                  <h3 className="font-semibold text-sm">설치될 도구 목록</h3>
                  {DUMMY_TOOLS.map((tool, index) => (
                    <div key={index} className="flex items-center justify-between p-3 bg-secondary/50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-primary/10 rounded-lg flex items-center justify-center">
                          <svg
                            className="w-4 h-4 text-primary"
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
                        <div>
                          <p className="font-medium text-sm">{tool.name}</p>
                          <p className="text-xs text-muted-foreground">v{tool.version}</p>
                        </div>
                      </div>
                      <span className="text-xs font-medium text-accent bg-accent/10 px-2 py-1 rounded-full">
                        {tool.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {isEnvironmentSet && (
            <div className="flex gap-4">
              <Button className="flex-1" onClick={() => router.push("/admin")}>
                홈으로 돌아가기
              </Button>
              <Button className="flex-1 bg-transparent" variant="outline" onClick={() => router.push("/admin/create")}>
                계정 생성하러 가기
              </Button>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
