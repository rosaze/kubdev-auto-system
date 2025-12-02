const API_BASE_URL = "http://localhost:8000"

// API 응답 타입 정의
export interface ApiResponse<T = any> {
  success: boolean
  data?: T
  error?: string
}

// 1. 로그인
export async function login(userCode: string): Promise<ApiResponse<{ user_type: string; user_id: string }>> {
  try {
    const response = await fetch(`${API_BASE_URL}/user/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ user_code: userCode }),
    })

    if (!response.ok) {
      const error = await response.json()
      return { success: false, error: error.detail || "로그인에 실패했습니다" }
    }

    const data = await response.json()
    return { success: true, data }
  } catch (error) {
    console.error("[v0] Login error:", error)
    return { success: false, error: "서버와 통신할 수 없습니다" }
  }
}

// 2. 관계자 계정 생성
export async function createAdminAccount(
  currentUserId: string,
): Promise<ApiResponse<{ user_id: string; user_code: string }>> {
  try {
    const response = await fetch(`${API_BASE_URL}/user/create`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        current_user_id: currentUserId,
        user_type: "admin",
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      return { success: false, error: error.detail || "관계자 계정 생성에 실패했습니다" }
    }

    const data = await response.json()
    return { success: true, data }
  } catch (error) {
    console.error("[v0] Create admin account error:", error)
    return { success: false, error: "서버와 통신할 수 없습니다" }
  }
}

// 3. 사용자 계정 생성
export async function createUserAccount(
  currentUserId: string,
  userId: string,
): Promise<ApiResponse<{ user_id: string; user_code: string }>> {
  try {
    const response = await fetch(`${API_BASE_URL}/user/create`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        current_user_id: currentUserId,
        user_type: "user",
        user_id: userId,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      return { success: false, error: error.detail || "사용자 계정 생성에 실패했습니다" }
    }

    const data = await response.json()
    return { success: true, data }
  } catch (error) {
    console.error("[v0] Create user account error:", error)
    return { success: false, error: "서버와 통신할 수 없습니다" }
  }
}

// 4. 계정 목록 조회
export async function getUserList(currentUserId: string): Promise<ApiResponse<any[]>> {
  try {
    const response = await fetch(`${API_BASE_URL}/user/list?current_user_id=${currentUserId}`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    })

    if (!response.ok) {
      const error = await response.json()
      return { success: false, error: error.detail || "계정 목록 조회에 실패했습니다" }
    }

    const data = await response.json()
    return { success: true, data }
  } catch (error) {
    console.error("[v0] Get user list error:", error)
    return { success: false, error: "서버와 통신할 수 없습니다" }
  }
}

// 5. YAML 파일 업로드
export async function uploadYaml(currentUserId: string, file: File): Promise<ApiResponse<any>> {
  try {
    const formData = new FormData()
    formData.append("current_user_id", currentUserId)
    formData.append("yaml", file)

    const response = await fetch(`${API_BASE_URL}/yaml/upload`, {
      method: "POST",
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json()
      return { success: false, error: error.detail || "YAML 파일 업로드에 실패했습니다" }
    }

    const data = await response.json()
    return { success: true, data }
  } catch (error) {
    console.error("[v0] Upload YAML error:", error)
    return { success: false, error: "서버와 통신할 수 없습니다" }
  }
}

// 6. Pod 삭제
export async function deletePod(currentUserId: string, targetUserId: string): Promise<ApiResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/pod/delete`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        current_user_id: currentUserId,
        target_user_id: targetUserId,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      return { success: false, error: error.detail || "Pod 삭제에 실패했습니다" }
    }

    const data = await response.json()
    return { success: true, data }
  } catch (error) {
    console.error("[v0] Delete pod error:", error)
    return { success: false, error: "서버와 통신할 수 없습니다" }
  }
}

// 7. Pod 재시작
export async function restartPod(currentUserId: string, targetUserId: string): Promise<ApiResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/pod/restart`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        current_user_id: currentUserId,
        target_user_id: targetUserId,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      return { success: false, error: error.detail || "Pod 재시작에 실패했습니다" }
    }

    const data = await response.json()
    return { success: true, data }
  } catch (error) {
    console.error("[v0] Restart pod error:", error)
    return { success: false, error: "서버와 통신할 수 없습니다" }
  }
}

// 8. 메트릭 조회
export async function getMetrics(userId: string): Promise<ApiResponse<any>> {
  try {
    const response = await fetch(`${API_BASE_URL}/metrics?user_id=${userId}`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    })

    if (!response.ok) {
      const error = await response.json()
      return { success: false, error: error.detail || "메트릭 조회에 실패했습니다" }
    }

    const data = await response.json()
    return { success: true, data }
  } catch (error) {
    console.error("[v0] Get metrics error:", error)
    return { success: false, error: "서버와 통신할 수 없습니다" }
  }
}

// 9. Pod 중지
export async function stopPod(currentUserId: string, targetUserId: string): Promise<ApiResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/pod/stop`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        current_user_id: currentUserId,
        target_user_id: targetUserId,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      return { success: false, error: error.detail || "Pod 중지에 실패했습니다" }
    }

    const data = await response.json()
    return { success: true, data }
  } catch (error) {
    console.error("[v0] Stop pod error:", error)
    return { success: false, error: "서버와 통신할 수 없습니다" }
  }
}
