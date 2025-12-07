const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

// API 응답 타입 정의
export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
}

interface LoginApiResponse {
  user_info: {
    id: number;
    name: string;
    role: string;
    last_login?: string | null;
  };
}

export interface EnvironmentSummary {
  id: number;
  user_id: number;
  name: string;
  status: string;
  k8s_namespace: string;
  access_url?: string | null;
  internal_ip?: string | null;
  external_port?: number | null;
  current_resource_usage?: {
    cpu_usage?: number;
    memory_usage?: number;
    storage_usage?: number;
  };
}

// 1. 로그인
export async function login(
  userCode: string
): Promise<ApiResponse<{ user_type: string; user_id: number; name: string; token: string }>> {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ access_code: userCode }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return { success: false, error: error.detail || "로그인에 실패했습니다" };
    }

    const data: LoginApiResponse = await response.json();
    const token = `${data.user_info.id}-${userCode.trim().toUpperCase()}`

    return {
      success: true,
      data: {
        user_id: data.user_info.id,
        user_type: data.user_info.role,
        name: data.user_info.name,
        token,
      },
    };
  } catch (error) {
    console.error("[frontend] Login error:", error);
    return { success: false, error: "서버와 통신할 수 없습니다" };
  }
}

// 2. 관계자 계정 생성
export async function createAdminAccount(
  currentUserId: string,
  name?: string
): Promise<ApiResponse<{ user_id: number; user_code: string }>> {
  try {
    const response = await fetch(`${API_BASE_URL}/users/admin`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        current_user_id: Number(currentUserId),
        name: name || `Admin-${Date.now()}`,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return {
        success: false,
        error: error.detail || "관계자 계정 생성에 실패했습니다",
      };
    }

    const data = await response.json();
    return {
      success: true,
      data: { user_id: data.id, user_code: data.access_code },
    };
  } catch (error) {
    console.error("[frontend] Create admin account error:", error);
    return { success: false, error: "서버와 통신할 수 없습니다" };
  }
}

// 3. 사용자 계정 생성
export async function createUserAccount(
  currentUserId: string,
  userId: string
): Promise<ApiResponse<{ user_id: number; user_code: string }>> {
  try {
    const response = await fetch(`${API_BASE_URL}/users/user`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        current_user_id: Number(currentUserId),
        name: userId,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return {
        success: false,
        error: error.detail || "사용자 계정 생성에 실패했습니다",
      };
    }

    const data = await response.json();
    return {
      success: true,
      data: { user_id: data.user.id, user_code: data.user.access_code },
    };
  } catch (error) {
    console.error("[frontend] Create user account error:", error);
    return { success: false, error: "서버와 통신할 수 없습니다" };
  }
}

// 4. 환경 목록 조회
export async function listEnvironments(
  userId?: string,
  token?: string
): Promise<ApiResponse<EnvironmentSummary[]>> {
  try {
    const params = new URLSearchParams({ size: "100" });
    if (userId) {
      params.append("user_id", userId);
    }

    const response = await fetch(
      `${API_BASE_URL}/environments?${params.toString()}`,
      {
        headers: token
          ? {
              Authorization: `Bearer ${token}`,
            }
          : undefined,
      }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return {
        success: false,
        error: error.detail || "환경 목록 조회에 실패했습니다",
      };
    }

    const data = await response.json();
    return { success: true, data: data.environments || [] };
  } catch (error) {
    console.error("[frontend] List environments error:", error);
    return { success: false, error: "서버와 통신할 수 없습니다" };
  }
}

// 5. YAML 파일 업로드 (템플릿 설정)
export async function uploadYaml(
  currentUserId: string,
  file: File
): Promise<ApiResponse<any>> {
  try {
    const formData = new FormData();
    formData.append("current_user_id", currentUserId);
    formData.append("yaml", file);

    const response = await fetch(`${API_BASE_URL}/templates/upload-yaml`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return {
        success: false,
        error: error.detail || "YAML 파일 업로드에 실패했습니다",
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    console.error("[frontend] Upload YAML error:", error);
    return { success: false, error: "서버와 통신할 수 없습니다" };
  }
}

// 6. 환경 액션 (중지/재시작/삭제)
export async function environmentAction(
  environmentId: number,
  action: "stop" | "restart" | "delete"
): Promise<ApiResponse> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/environments/${environmentId}/actions`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ action }),
      }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return {
        success: false,
        error: error.detail || "환경 액션 실행에 실패했습니다",
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    console.error("[frontend] Environment action error:", error);
    return { success: false, error: "서버와 통신할 수 없습니다" };
  }
}

// 7. 메트릭 조회 (환경 기준)
export async function getEnvironmentMetrics(
  environmentId: number
): Promise<ApiResponse<any>> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/monitoring/environments/${environmentId}/metrics`
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return {
        success: false,
        error: error.detail || "메트릭 조회에 실패했습니다",
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    console.error("[frontend] Get metrics error:", error);
    return { success: false, error: "서버와 통신할 수 없습니다" };
  }
}

// 8. 모든 환경 메트릭 조회 (모니터링용 - 인증 없음)
export async function getAllEnvironmentMetrics(): Promise<ApiResponse<any[]>> {
  try {
    const response = await fetch(`${API_BASE_URL}/monitoring/metrics`);

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return {
        success: false,
        error: error.detail || "메트릭 조회에 실패했습니다",
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    console.error("[frontend] Get all metrics error:", error);
    return { success: false, error: "서버와 통신할 수 없습니다" };
  }
}

// 9. 사용자별 환경 목록 조회 (모니터링용)
export async function getUserEnvironments(
  userId: number
): Promise<ApiResponse<any>> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/monitoring/user/${userId}/environments`
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return {
        success: false,
        error: error.detail || "환경 목록 조회에 실패했습니다",
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    console.error("[frontend] Get user environments error:", error);
    return { success: false, error: "서버와 통신할 수 없습니다" };
  }
}

// 10. YAML 파일로 템플릿 생성
export async function createTemplateFromYaml(
  templateName: string,
  yamlFile: File,
  currentUserId: string,
  gitRepository?: string
): Promise<ApiResponse<any>> {
  try {
    const formData = new FormData();
    formData.append("template_name", templateName);
    formData.append("yaml_file", yamlFile);
    formData.append("created_by", currentUserId);
    if (gitRepository) {
      formData.append("git_repository", gitRepository);
    }

    const response = await fetch(`${API_BASE_URL}/templates/create-from-yaml`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return {
        success: false,
        error: error.detail || "템플릿 생성에 실패했습니다",
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    console.error("[frontend] Create template from YAML error:", error);
    return { success: false, error: "서버와 통신할 수 없습니다" };
  }
}

// 11. 사용자 + 환경 통합 생성 (새로운 엔드포인트)
export async function createUserWithEnvironment(
  userName: string,
  templateId: number
): Promise<ApiResponse<{ user_id: number; access_code: string; environment_id: number }>> {
  try {
    const response = await fetch(`${API_BASE_URL}/users/user-with-environment`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: userName,
        template_id: templateId,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      return {
        success: false,
        error: error.detail || "사용자 및 환경 생성에 실패했습니다",
      };
    }

    const data = await response.json();
    return {
      success: true,
      data: {
        user_id: data.user_id,
        access_code: data.access_code,
        environment_id: data.environment_id,
      },
    };
  } catch (error) {
    console.error("[frontend] Create user with environment error:", error);
    return { success: false, error: "서버와 통신할 수 없습니다" };
  }
}

// Server-Sent Events를 사용한 실시간 환경 생성
export interface StreamEvent {
  status: string;
  message: string;
  user_id?: number;
  access_code?: string;
  environment_id?: number;
  url?: string;
}

export function createUserWithEnvironmentStream(
  userName: string,
  templateId: number,
  onMessage: (event: StreamEvent) => void,
  onComplete: (data: { user_id: number; access_code: string; environment_id: number; url?: string }) => void,
  onError: (error: string) => void
): () => void {
  const eventSource = new EventSource(
    `${API_BASE_URL}/users/user-with-environment/stream?name=${encodeURIComponent(userName)}&template_id=${templateId}`
  );

  eventSource.onmessage = (event) => {
    try {
      const data: StreamEvent = JSON.parse(event.data);

      if (data.status === 'error') {
        onError(data.message);
        eventSource.close();
      } else if (data.status === 'completed' || data.status === 'timeout') {
        if (data.user_id && data.access_code && data.environment_id) {
          onComplete({
            user_id: data.user_id,
            access_code: data.access_code,
            environment_id: data.environment_id,
            url: data.url
          });
        }
        eventSource.close();
      } else {
        onMessage(data);
      }
    } catch (e) {
      console.error('Failed to parse SSE message:', e);
    }
  };

  eventSource.onerror = () => {
    onError('서버 연결이 끊어졌습니다');
    eventSource.close();
  };

  return () => eventSource.close();
}
