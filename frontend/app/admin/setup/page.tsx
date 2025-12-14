"use client"

import type React from "react"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { createTemplateFromYaml } from "@/lib/api"

export default function AdminSetupPage() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)
  const [templateName, setTemplateName] = useState("")
  const [environmentFile, setEnvironmentFile] = useState<File | null>(null)
  const [isEnvironmentSet, setIsEnvironmentSet] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState("")
  const [createdTemplate, setCreatedTemplate] = useState<any>(null)
  const [showRawResponse, setShowRawResponse] = useState(false)

  const renderValue = (value: any) => {
    if (value === null || value === undefined) return "없음"
    if (typeof value === "object") {
      return (
        <pre className="text-xs font-mono whitespace-pre-wrap break-words bg-muted/40 p-2 rounded border border-border/60">
          {JSON.stringify(value, null, 2)}
        </pre>
      )
    }
    return String(value)
  }

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

  const handleEnvironmentFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0]
      setEnvironmentFile(file)
      setUploadError("")
    }
  }

  const handleCreateTemplate = async () => {
    if (!templateName.trim()) {
      setUploadError("템플릿 이름을 입력해주세요.")
      return
    }

    if (!environmentFile) {
      setUploadError("YAML 파일을 선택해주세요.")
      return
    }

    setIsUploading(true)
    setUploadError("")

    const userId = localStorage.getItem("userId")
    if (!userId) {
      setUploadError("사용자 정보를 찾을 수 없습니다. 다시 로그인해주세요.")
      setIsUploading(false)
      return
    }

    const result = await createTemplateFromYaml(templateName, environmentFile, userId)

    if (result.success) {
      setIsEnvironmentSet(true)
      setCreatedTemplate(result.data)
      localStorage.setItem("environmentSet", "true")
    } else {
      setUploadError(result.error || "템플릿 생성에 실패했습니다")
    }

    setIsUploading(false)
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
              <div className="space-y-2">
                <label htmlFor="template-name" className="text-sm font-medium">
                  템플릿 이름
                </label>
                <Input
                  id="template-name"
                  type="text"
                  placeholder="예: Python 개발 환경"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  disabled={isUploading}
                />
              </div>

              <div className="border-2 border-dashed border-border rounded-lg p-8 text-center hover:border-primary transition-colors">
                <input
                  type="file"
                  accept=".yaml,.yml"
                  onChange={handleEnvironmentFileChange}
                  className="hidden"
                  id="environment-file-upload"
                  disabled={isUploading}
                />
                <label htmlFor="environment-file-upload" className={isUploading ? "cursor-not-allowed" : "cursor-pointer"}>
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
                      <p className="font-medium">클릭하여 YAML 파일 선택</p>
                      <p className="text-sm text-muted-foreground">.yaml 또는 .yml 파일</p>
                    </div>
                  </div>
                </label>
              </div>

              {environmentFile && (
                <Button
                  onClick={handleCreateTemplate}
                  disabled={isUploading}
                  className="w-full"
                >
                  {isUploading ? "템플릿 생성 중..." : "템플릿 생성"}
                </Button>
              )}

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

              {environmentFile && (
                <div className="flex items-center gap-2 p-3 bg-secondary rounded-lg">
                  <svg
                    className="w-5 h-5 text-muted-foreground"
                    fill="none"
                    strokeWidth="2"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                    />
                  </svg>
                  <span className="font-medium">{environmentFile.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">선택됨</span>
                </div>
              )}

              {createdTemplate && (
                <div className="space-y-3 mt-4 pt-4 border-t">
                  <div className="flex items-center gap-2 p-3 bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300 rounded-lg">
                    <svg
                      className="w-5 h-5"
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
                    <span className="font-medium">템플릿이 성공적으로 생성되었습니다!</span>
                  </div>

                  <h3 className="font-semibold text-sm">생성된 템플릿 정보</h3>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between p-3 bg-secondary/50 rounded-lg">
                      <span className="text-sm text-muted-foreground">템플릿 ID</span>
                      <span className="font-medium">{createdTemplate.id}</span>
                    </div>
                    <div className="flex items-center justify-between p-3 bg-secondary/50 rounded-lg">
                      <span className="text-sm text-muted-foreground">이름</span>
                      <span className="font-medium">{createdTemplate.name}</span>
                    </div>
                    <div className="flex items-center justify-between p-3 bg-secondary/50 rounded-lg">
                      <span className="text-sm text-muted-foreground">상태</span>
                      <span className="text-xs font-medium text-green-600 bg-green-100 dark:bg-green-950 dark:text-green-300 px-2 py-1 rounded-full">
                        {createdTemplate.status}
                      </span>
                    </div>
                    <div className="flex items-center justify-between p-3 bg-secondary/50 rounded-lg">
                      <span className="text-sm text-muted-foreground">Docker 이미지</span>
                      <span className="font-mono text-xs">{createdTemplate.base_image}</span>
                    </div>
                    {createdTemplate.default_git_repo && (
                      <div className="flex items-center justify-between p-3 bg-secondary/50 rounded-lg">
                        <span className="text-sm text-muted-foreground">Git 저장소</span>
                        <span className="font-mono text-xs truncate max-w-[200px]">{createdTemplate.default_git_repo}</span>
                      </div>
                    )}
                    {Object.entries(createdTemplate)
                      .filter(([key]) => !["id", "name", "status", "base_image", "default_git_repo"].includes(key))
                      .map(([key, value]) => (
                        <div key={key} className="space-y-1 p-3 bg-secondary/50 rounded-lg">
                          <div className="flex items-center justify-between gap-4">
                            <span className="text-sm text-muted-foreground">{key}</span>
                            {typeof value !== "object" && (
                              <span className="font-mono text-xs max-w-[200px] truncate text-right">{String(value)}</span>
                            )}
                          </div>
                          {typeof value === "object" && renderValue(value)}
                        </div>
                      ))}
                  </div>

                  <div className="space-y-2">
                    <Button variant="outline" className="w-full" onClick={() => setShowRawResponse((prev) => !prev)}>
                      {showRawResponse ? "응답 전문 숨기기" : "응답 전문 보기"}
                    </Button>
                    {showRawResponse && (
                      <pre className="bg-secondary/60 rounded-lg p-3 text-xs font-mono whitespace-pre-wrap break-words border border-border/80 max-h-96 overflow-auto">
                        {JSON.stringify(createdTemplate, null, 2)}
                      </pre>
                    )}
                  </div>
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
