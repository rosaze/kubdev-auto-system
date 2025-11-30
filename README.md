# KubeDev Auto System

K8s 기반 자동 개발 환경 프로비저닝 B2B SaaS 플랫폼

## 🏗️ 프로젝트 구조

```
kubdev-auto-system/
├── frontend/              # React 기반 대시보드 (추후 구현)
├── backend/               # FastAPI 백엔드 서버
│   ├── app/
│   │   ├── api/          # API 엔드포인트
│   │   ├── core/         # 핵심 설정 및 유틸리티
│   │   ├── models/       # 데이터베이스 모델
│   │   ├── services/     # 비즈니스 로직
│   │   └── schemas/      # Pydantic 스키마
│   ├── k8s/              # K8s 관련 유틸리티
│   ├── requirements.txt
│   ├── Dockerfile
│   └── main.py
├── k8s/                   # 플랫폼 배포용 K8s YAML
│   ├── deployments/
│   ├── services/
│   ├── configmaps/
│   └── rbac/
├── docker-compose.yml     # 로컬 개발환경
└── docs/                  # 문서
```

## 🎯 주요 기능

### 1. 일대일 신입부원 온보딩
- 팀 리더가 사전 정의한 개발 환경 템플릿
- 원클릭 환경 생성 및 웹 IDE 접속
- 자동화된 초기 설정 스크립트 실행

### 2. 대규모 교육/부트캠프 지원
- 다중 사용자 동시 환경 생성
- 리소스 할당 및 제한 관리
- 실시간 모니터링 및 관리

### 3. 외부 개발자 협업
- 제한된 네트워크 및 DB 접근
- 임시 환경 생성 및 자동 정리
- 보안 정책 적용

## 🚀 시스템 플로우

1. **Admin**: 프로젝트 템플릿 및 리소스 정책 설정
2. **User**: 프로젝트 선택 및 환경 생성 요청
3. **Backend**: K8s 클러스터에 개발환경 Pod 배포
4. **K8s**:
   - Init Container: Git 저장소 클론
   - Main Container: 웹 IDE (VS Code Server) 실행
5. **User**: 브라우저를 통한 IDE 접속 및 개발

## 🛠️ 기술 스택

- **Backend**: Python FastAPI + Kubernetes Python Client
- **Database**: PostgreSQL
- **Container Orchestration**: Kubernetes + Helm
- **IDE**: VS Code Server (Web-based)
- **Proxy**: Nginx Ingress Controller
- **Monitoring**: Prometheus + Grafana

## 📋 개발 계획

1. **Phase 1**: 백엔드 API 및 K8s 통합
2. **Phase 2**: 템플릿 시스템 구현
3. **Phase 3**: 모니터링 및 리소스 관리
4. **Phase 4**: 보안 및 네트워크 정책
5. **Phase 5**: 프론트엔드 대시보드 (추후)

## 🔧 개발 환경 설정

#### 백엔드 서버 실행
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### 프론트엔드 실행
```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

#### Docker Compose로 전체 스택 실행
```bash
docker compose up -d
```

#### 초기 사용자 생성(데이터베이스)
```bash
# 1. docker-compose를 통해 PostgreSQL 실행
# 2. 백엔드 서버 최초 1회 실행 -> 테이블 생성됨
cd backend
python3 create_initial_user.py
```

## 📚 API 문서

서버 실행 후 `http://localhost:8000/docs`에서 Swagger UI로 API 문서 확인 가능 
