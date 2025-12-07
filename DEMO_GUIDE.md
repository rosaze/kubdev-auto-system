# KubeDev 시스템 시연 가이드

## 🎯 시연 시나리오

### 관리자(Admin) 시연
1. ✅ YAML 템플릿 업로드
2. ✅ 검증 환경 확인
3. ✅ 사용자 계정 생성
4. ✅ 접속 코드 발급

### 사용자(User) 시연
1. ✅ 5자리 코드로 로그인
2. ✅ "IDE 열기" 버튼 클릭
3. ✅ VSCode 웹에서 즉시 코딩 시작
4. ✅ Git 레포지토리 자동 클론 확인
5. ✅ 파일 수정 및 저장

---

## 📋 시연 준비사항

### 1. 시스템 실행 확인
```bash
# 백엔드
docker-compose ps
# ✅ backend: Up
# ✅ db: Up

# 프론트엔드
curl http://localhost:3001
# ✅ 200 OK

# Kubernetes
kubectl get pods -n kubedev-system
# ✅ kubedev-controller: Running

# 헬스체크
curl http://localhost:8000/health
# ✅ database: connected
# ✅ kubernetes: connected
```

### 2. 테스트 YAML 파일 준비

현재 작동하는 YAML (Python 미설치 이슈):
- `test_crd_env.yaml` - Git 클론 및 code-server 시작 ✅
- `demo_python_ml.yaml` - Python이 없어서 라이브러리 설치 실패 ❌

**해결 방법**: Node.js는 code-server 이미지에 기본 포함!

**시연용 Node.js 템플릿** (`demo_nodejs.yaml`):
```yaml
apiVersion: kubedev.my-project.com/v1alpha1
kind: KubeDevEnvironment
metadata:
  name: demo-nodejs-env
  namespace: kubdev-users
spec:
  userName: "demo-student"
  gitRepository: "https://github.com/vercel/next.js.git"
  image: "codercom/code-server:latest"

  commands:
    init: |
      echo "========================================="
      echo "📦 Node.js 환경 설정 시작..."
      echo "========================================="

      cd /workspace

      # Node.js 버전 확인
      echo "✅ Node.js 버전:"
      node --version

      # npm 버전 확인
      echo "✅ npm 버전:"
      npm --version

      # 간단한 package.json 생성 (데모용)
      echo '{
        "name": "demo-project",
        "version": "1.0.0",
        "description": "KubeDev 데모 프로젝트",
        "main": "index.js",
        "scripts": {
          "start": "node index.js"
        },
        "dependencies": {
          "express": "^4.18.2"
        }
      }' > package.json

      # 라이브러리 설치
      echo "📚 Express.js 설치 중..."
      npm install

      # 설치 확인
      echo ""
      echo "✅ 설치 완료!"
      echo "-----------------------------------"
      ls -la node_modules | head -10
      echo "-----------------------------------"
      echo ""
      echo "🎉 환경 설정이 완료되었습니다!"
      echo "========================================="

    start: ""

  ports:
    - 8080
    - 3000

  storage:
    size: "10Gi"
```

---

## 🎬 시연 스크립트

### Part 1: 관리자 화면 (5분)

#### 1. 로그인
```
URL: http://localhost:3001
접속 코드: admin (또는 생성된 관리자 코드)
```

**시연 포인트**:
- "저희 시스템은 접속 코드 기반 인증을 사용합니다"
- "관리자는 5자리 코드로 즉시 로그인 가능합니다"

#### 2. YAML 템플릿 업로드
```
파일: demo_nodejs.yaml
위치: 메인 페이지 "템플릿 등록 (YAML)" 섹션
```

**시연 대사**:
```
"관리자가 수업 환경을 YAML 파일로 정의합니다"
"여기에는 Git 레포지토리, 사용할 라이브러리, 실행 명령 등이 포함됩니다"
"업로드하면 자동으로 검증 환경이 생성됩니다"
```

**실행**:
1. YAML 파일 선택
2. "업로드" 클릭
3. 성공 메시지 확인: "템플릿이 생성되고 환경이 검증되었습니다"

**백엔드 확인** (선택사항):
```bash
# 템플릿 확인
curl http://localhost:8000/api/v1/templates

# Kubernetes Pod 확인
kubectl get pods -n kubdev-users
```

#### 3. 사용자 계정 생성
```
위치: "사용자 관리" 탭
사용자 이름: "김철수"
```

**시연 대사**:
```
"이제 학생 계정을 생성합니다"
"학생 이름만 입력하면 시스템이 자동으로:"
"1. 5자리 접속 코드 발급"
"2. 개인 개발 환경 생성"
"3. Git 레포지토리 클론"
"4. 필요한 라이브러리 설치"
"를 모두 자동으로 처리합니다"
```

**실행**:
1. 사용자 이름 입력: "김철수"
2. "생성" 클릭
3. **접속 코드 복사** (예: `AB12C`)
4. 성공 메시지 확인

**Kubernetes 확인** (선택사항):
```bash
# 사용자 환경 Pod 확인
kubectl get pods -n kubedev-users

# CRD 상태 확인
kubectl get kubedevenvironments -A
```

#### 4. 환경 목록 확인
```
위치: 대시보드 또는 환경 목록
```

**시연 포인트**:
- 생성된 환경 상태: "Running"
- CPU/메모리 사용량 표시
- "IDE 열기" 버튼 확인

---

### Part 2: 사용자 화면 (3분)

#### 1. 로그인
```
URL: http://localhost:3001
접속 코드: AB12C (관리자가 발급한 코드)
```

**시연 대사**:
```
"학생은 관리자로부터 받은 5자리 코드만 입력하면 됩니다"
"별도의 회원가입이나 설정 없이 즉시 사용 가능합니다"
```

#### 2. IDE 열기
```
위치: 사용자 홈 화면
버튼: "VS Code 환경 접속"
```

**시연 대사**:
```
"이미 모든 준비가 완료되었습니다"
"IDE 열기 버튼만 클릭하면..."
```

**실행**:
1. "VS Code 환경 접속" 버튼 클릭
2. 새 탭에서 VSCode 웹 자동 열림

#### 3. VSCode 웹 시연
```
확인 사항:
✅ /workspace 폴더 자동 열림
✅ Git 레포지토리 파일 표시
✅ 터미널 사용 가능
✅ node_modules 설치됨 (라이브러리)
```

**시연 대사**:
```
"보시는 것처럼:"
"1. Git 레포지토리가 이미 클론되어 있고"
"2. 필요한 라이브러리(node_modules)가 이미 설치되어 있습니다"
"3. 학생은 바로 코딩을 시작할 수 있습니다"
```

**실시간 코딩 데모**:
1. 터미널 열기 (Ctrl+`)
2. `node --version` 실행
3. `npm list` 실행 (설치된 패키지 확인)
4. 새 파일 생성: `app.js`
5. 간단한 코드 작성:
```javascript
const express = require('express');
const app = express();

app.get('/', (req, res) => {
  res.send('Hello KubeDev!');
});

app.listen(3000, () => {
  console.log('Server running on port 3000');
});
```
6. 저장 (Ctrl+S)
7. 터미널에서 실행: `node app.js`

---

## 🔥 핵심 메시지 (30초 요약)

```
"KubeDev는 Kubernetes 기반 자동 개발 환경 프로비저닝 시스템입니다"

"관리자는 YAML 하나로 수업 환경을 정의하고"
"학생은 5자리 코드만으로 즉시 사용할 수 있습니다"

"모든 환경은 격리되어 있고"
"필요한 라이브러리는 자동으로 설치되며"
"VSCode 웹으로 어디서든 접속 가능합니다"

"설정 시간 0분, 학생은 바로 코딩을 시작합니다"
```

---

## 📊 강조할 기술 요소

### 1. Kubernetes CRD (Custom Resource Definition)
- 선언적 환경 정의
- Controller가 자동으로 리소스 생성
- 표준 Kubernetes API 사용

### 2. GitOps
- Git 레포지토리가 단일 진실 소스
- YAML로 인프라 코드화
- 버전 관리 가능

### 3. 자동화
- Zero-configuration for students
- 라이브러리 자동 설치
- 환경 자동 프로비저닝

### 4. 격리 (Isolation)
- 각 학생마다 독립적인 Namespace
- CPU/메모리 리소스 제한
- 네트워크 격리

### 5. 웹 기반 IDE
- 브라우저만 있으면 OK
- 로컬 설정 불필요
- ChromeOS, iPad에서도 사용 가능

---

## 🐛 시연 중 발생 가능한 이슈

### Issue 1: Pod가 Pending 상태
**원인**: Kubernetes 리소스 부족
**해결**:
```bash
kubectl describe pod <pod-name> -n <namespace>
# 리소스 요청량 조정 필요
```

### Issue 2: code-server 접속 불가
**원인**: minikube service 터널 끊김
**해결**:
```bash
minikube service <service-name> -n <namespace> --url
# 새 URL 사용
```

### Issue 3: 라이브러리 설치 실패
**원인**: 이미지에 Python/Node.js 없음
**해결**:
- Node.js 사용 (code-server에 기본 포함)
- 또는 커스텀 이미지 사용

### Issue 4: Git 클론 실패
**원인**: Private 레포지토리
**해결**: Public 레포지토리 사용 또는 credentials 설정

---

## 📝 Q&A 대비

### Q1: "로컬 PC에 설치해야 하나요?"
A: 아닙니다. 브라우저만 있으면 됩니다. 모든 환경은 클라우드(Kubernetes)에서 실행됩니다.

### Q2: "학생이 잘못 건드려서 환경이 망가지면?"
A: 관리자가 "재시작" 버튼으로 1초만에 초기 상태로 복구 가능합니다.

### Q3: "몇 명까지 동시 사용 가능한가요?"
A: Kubernetes 클러스터 리소스에 따라 다릅니다. 현재 설정은 학생당 CPU 1코어, 메모리 2GB입니다.

### Q4: "과제 제출은 어떻게 하나요?"
A: Git에 commit & push 하도록 안내합니다. 또는 별도 제출 시스템과 연동 가능합니다.

### Q5: "비용은 얼마나 드나요?"
A: 클라우드 제공업체에 따라 다릅니다. 온프레미스 Kubernetes면 추가 비용 없습니다.

### Q6: "VSCode Extension 설치 가능한가요?"
A: 네, code-server는 대부분의 VSCode Extension을 지원합니다.

### Q7: "인터넷이 느리면 어떻게 되나요?"
A: VSCode 웹은 텍스트 기반이라 트래픽이 적습니다. 일반적인 모바일 데이터로도 사용 가능합니다.

---

## 🎥 시연 동영상 촬영 팁

1. **화면 녹화 설정**: 1920x1080, 30fps
2. **브라우저 줌**: 125% (가독성)
3. **터미널 폰트 크기**: 18pt 이상
4. **마우스 커서 강조**: 활성화
5. **타이핑 속도**: 천천히, 명확하게
6. **전환**: 관리자 화면 → 사용자 화면 간 부드럽게

---

## 작성일: 2025-12-03
## 프로젝트: KubeDev Auto System
