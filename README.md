# Oxidizer: Human-Insight Guided C-to-Rust Transpiler

## Docker deployment

Build the image:

```bash
docker build -t oxidizer:latest .
```

The Docker image uses `requirements-docker.txt` to avoid installing GPU/CUDA packages that are not needed for this CPU-based deployment.

Create local input and output folders:

```bash
mkdir -p input output
```

Copy your C source file into `input/`, then run the container:

```bash
docker run --rm \
  --env-file .env \
  -v "$(pwd)/input:/app/data/inputs" \
  -v "$(pwd)/output:/app/data/outputs" \
  oxidizer:latest \
  --target example.c
```

On Windows PowerShell:

```powershell
docker run --rm `
  --env-file .env `
  -v ${PWD}/input:/app/data/inputs `
  -v ${PWD}/output:/app/data/outputs `
  oxidizer:latest `
  --target example.c
```

The current CLI reads C files from `/app/data/inputs` and writes generated Rust artifacts under `/app/data/outputs`.

Use `.env.example` as a template for local API keys. Do not commit a real `.env` file.

> 인간 통찰력 기반 LLM 제어를 통한 C 코드의 관용적(Idiomatic) Rust 자동 변환 파이프라인
> 
> 
> 캡스톤 디자인 프로젝트 (팀명: Oxidizer)
> 

## 1. 프로젝트 개발 목표 (Project Goals)

본 프로젝트의 최우선 목표는 사용자가 C 소스 코드를 제공했을 때, 사람의 개입 없이 최종적으로 메모리 안전성이 보장된 Rust 코드를 반환하는 **'End-to-End 자동화 파이프라인'**을 구축하는 것입니다. 기존 정적 변환 도구(C2Rust)의 한계와 LLM의 환각 현상을 극복하기 위해, 인간이 분석한 실패 패턴(Insight)을 영어 기반의 프롬프트로 LLM에 주입하여 변환을 제어합니다.

1. **완전 자동화 파이프라인 구축 (최우선):** C 소스 코드 입력부터 정적 변환, LLM API 호출, 컴파일 에러 피드백 루프, 최종 결과물 출력까지 전 과정을 통제하는 메인 엔진(Orchestrator) 개발.
2. **영문 기반 통찰력 주입 (Prompt Engineering):** C2Rust가 남긴 `unsafe` 블록과 Raw Pointer를 식별하고, 이를 Safe Rust로 승격(Lifting)시키기 위한 구체적인 영문 가이드라인(Insight Prompts) 설계.
3. **일반화 성능 검증:** 함수 단위의 벤치마크(CRUST-bench)에서 파이프라인을 고도화한 뒤, 실무 수준의 복잡도(Syzygy_Zopfli)로 확장하여 성능 검증.

## 2. 핵심 기능 및 파이프라인 (Core Features & Pipeline)

### 전체 파이프라인 흐름도 (Architecture)

```
[User Input] C Source Code (.c)
   │
   ▼
[Main Engine] Automation Orchestrator (Python)
   │
   ├─► [Step 1: 정적 변환] C2Rust Transpiler 실행
   │     └─ 결과: 기능은 동일하지만 `unsafe`로 가득 찬 1차 Rust 코드
   │
   ├─► [Step 2: 통찰력 주입] Prompt Generator
   │     └─ 인간이 분석한 C-to-Rust 변환 패턴 가이드(English) 동적 결합
   │
   ├─► [Step 3: LLM 리팩토링] LLM API 연동 (GPT-4o / Gemini 등)
   │     └─ 결과: 안전성과 관용성이 부여된 2차 Rust 코드
   │
   └─► [Step 4: 검증 및 피드백] Cargo Compiler (rustc) 검증
         ├─ [에러 발생 시] 컴파일 에러 로그 파싱 -> LLM 재수정 요청 (Feedback Loop)
         └─ [컴파일 성공 시] 최종 Safe Rust 소스코드 반환 및 사용자 출력 (.rs)
```

### 주요 컴포넌트 (Key Components)

- **Main Pipeline Orchestrator:** 파이프라인의 전체 상태를 관리하고 각 모듈(C2Rust, LLM API, Compiler) 간의 데이터 흐름을 제어하는 핵심 엔진.
- **Base Translator Module:** C2Rust CLI를 Python 서브프로세스로 호출하고 결과물을 파싱.
- **Prompting & API Controller:** 영어로 작성된 통찰력 프롬프트 템플릿을 관리하고, LLM API 호출의 비동기 처리 및 토큰/비용 최적화를 담당.
- **Auto-Repair Loop:** 코드를 `cargo check`로 검증하고, 발생한 에러 로그를 분석하여 LLM에게 수정을 지시하는 자동 복구 루틴.

## 3. 항목별 개발 요구사항 (Requirements)

### 3.1. 기능적 요구사항 (Functional Requirements)

| **ID** | **요구사항 명** | **상세 내용** | **우선순위** |
| --- | --- | --- | --- |
| F-01 | 메인 엔진 제어기 구현 | 사용자의 단일 명령어 실행으로 전체 파이프라인이 순차적으로 작동하는 컨트롤러 스크립트 구축 | High |
| F-02 | LLM API 자동화 | Python 환경에서 지정된 LLM API와 통신하며 대량의 변환 요청을 안정적으로 처리 | High |
| F-03 | 영문 프롬프트 템플릿 | 문자열, 배열, 구조체 등 핵심 패턴에 대한 Insight Prompt를 영어로 작성 및 모듈화 관리 | High |
| F-04 | 자동 컴파일 검증 | 생성된 코드를 대상으로 백그라운드에서 `cargo check`를 실행하여 컴파일 가능 여부 판단 | High |
| F-05 | 에러 피드백 루프 | 컴파일 실패 시 stderr 로그를 파싱하고, 이를 프롬프트에 결합하여 재시도하는 로직 구현 (최대 반복 횟수 제한) | High |
| F-06 | 최종 결과물 반환 | 파이프라인 종료 시 원본 코드와 변환된 `.rs` 코드 비교본을 사용자 디렉토리에 명확히 저장 및 안내 | High |

### 3.2. 비기능적 요구사항 (Non-Functional Requirements)

| **ID** | **요구사항 명** | **상세 내용** | **우선순위** |
| --- | --- | --- | --- |
| NF-01 | 모듈화된 설계 | 메인 엔진과 각 파이프라인 단계(변환, API 요청, 검증)는 독립적인 모듈로 분리되어야 함 | High |
| NF-02 | 확장성 보장 | 새로운 실패 패턴이나 프롬프트 규칙이 발견될 경우, 핵심 엔진 수정 없이 템플릿 추가만으로 동작해야 함 | High |
| NF-03 | API 예외 처리 | 네트워크 지연, API 호출 한도 초과(Rate Limit) 등에 대비한 재시도(Retry) 및 예외 처리 로직 구현 | Medium |

## 4. 기술 스택 (Tech Stack)

- **Core Languages:** `Python 3.10+` (Main Engine & Automation), `Rust` (Target Language), `C` (Source Language)
- **Transpiler & Build Tools:** `C2Rust`, `Cargo`
- **LLM APIs:** `OpenAI API (GPT-4o)` or `Google Gemini API`
- **Environment:** `Linux/Ubuntu` or `WSL2` (C2Rust 호환성 및 파이프라인 구동용)

## 5. 단계별 개발 마일스톤 (3개월 / 약 12주 계획)

- [ ]  **Month 1 (1~4주차): 메인 파이프라인 MVP 구축**
    - C2Rust 설치 및 로컬 변환 환경 세팅
    - [Main Engine] C 코드 로드 -> C2Rust 실행 -> LLM API 호출 -> 결과물 저장에 이르는 기본 파이썬 컨트롤러 스크립트 작성
    - 소규모 C 코드 대상 기초 변환 테스트 및 API 연동 안정성 확보
- [ ]  **Month 2 (5~8주차): 영문 Insight Prompting 및 피드백 루프 구현**
    - CRUST-bench 데이터셋을 활용하여 `unsafe` 발생 주요 실패 패턴 수동 분석
    - 분석 결과를 바탕으로 최적화된 영문 Insight Prompt 작성 및 Prompt Generator 모듈 연동
    - 컴파일 에러 발생 시 로그를 파싱하여 LLM에 재요청하는 Auto-Repair (Feedback) Loop 통합
- [ ]  **Month 3 (9~12주차): 대규모 검증 및 최종 고도화**
    - 배치(Batch) 처리 스크립트 작성을 통한 대량의 파일 변환 자동화
    - Syzygy_Zopfli 등 실무 복잡도 코드 대상 일반화 성능 검증 (컴파일 성공률 및 unsafe 감소율 정량 평가)
    - 파이프라인 코드 리팩토링, 사용자 친화적 출력 포맷 적용 및 최종 결과보고서 작성

## 6. 최종 배포 및 활용 계획 (Deployment Plan)

- 본 프로젝트는 누구나 쉽게 C-to-Rust 변환 파이프라인을 사용할 수 있도록 Docker 기반의 배포 환경을 제공할 예정입니다.
    - 격리된 환경 제공: 사용자는 로컬 환경에 C2Rust, Rust Toolchain, Python 등을 복잡하게 설치할 필요가 없습니다.
    - 원클릭 실행: 제공되는 Dockerfile을 빌드하고 실행 명령어(docker run ...)에 C 소스 코드 경로만 넘겨주면, 컨테이너 내부에서 변환 파이프라인이 즉시 가동되어 최종 .rs 파일만 사용자에게 반환됩니다.
    - 재현성 보장: OS(Windows, Mac, Linux)에 구애받지 않고 동일한 변환 품질과 동작을 보장합니다.
