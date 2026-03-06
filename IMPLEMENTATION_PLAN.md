# Oxidizer 통합 기획서 및 구현 계획

본 문서는 Oxidizer 프로젝트의 전체 개발 청사진을 담은 통합 기획서입니다.
본 프로젝트는 인간의 변환 통찰력(Human Insight)을 기반으로 한 **'C-to-Rust 자동화 프롬프트 엔진'**을 흔들리지 않는 핵심 코어(Core Backbone)로 삼습니다. 이를 1차적으로 완벽히 구현한 뒤, 순수 프롬프트 변환이 가지는 한계(대용량 컨텍스트 소실, 복잡한 타입 추론 실패 등)를 극복하기 위해 최신 SOTA 논문들의 기법을 **성능 고도화 모듈(Advanced Enhancements)**로 점진적 통합하는 전략을 취합니다.

# [Part 1] 핵심 프로젝트 계획 (Core Plan - README.md)

> 프로젝트의 메인 목표이자 베이스라인이 되는 핵심 개발 계획입니다.
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

| ID | 요구사항 명 | 상세 내용 | 우선순위 |
| --- | --- | --- | --- |
| **F-01** | 메인 엔진 제어기 구현 | 사용자의 단일 명령어 실행으로 전체 파이프라인이 순차적으로 작동하는 컨트롤러 스크립트 구축 | High |
| **F-02** | LLM API 자동화 | Python 환경에서 지정된 LLM API와 통신하며 대량의 변환 요청을 안정적으로 처리 | High |
| **F-03** | 영문 프롬프트 템플릿 | 문자열, 배열, 구조체 등 핵심 패턴에 대한 Insight Prompt를 영어로 작성 및 모듈화 관리 | High |
| **F-04** | 자동 컴파일 검증 | 생성된 코드를 대상으로 백그라운드에서 `cargo check`를 실행하여 컴파일 가능 여부 판단 | High |
| **F-05** | 에러 피드백 루프 | 컴파일 실패 시 stderr 로그를 파싱하고, 이를 프롬프트에 결합하여 재시도하는 로직 구현 (최대 반복 횟수 제한) | High |
| **F-06** | 최종 결과물 반환 | 파이프라인 종료 시 원본 코드와 변환된 `.rs` 코드 비교본을 사용자 디렉토리에 명확히 저장 및 안내 | High |

### 3.2. 비기능적 요구사항 (Non-Functional Requirements)

| ID | 요구사항 명 | 상세 내용 | 우선순위 |
| --- | --- | --- | --- |
| **NF-01** | 모듈화된 설계 | 메인 엔진과 각 파이프라인 단계(변환, API 요청, 검증)는 독립적인 모듈로 분리되어야 함 | High |
| **NF-02** | 확장성 보장 | 새로운 실패 패턴이나 프롬프트 규칙이 발견될 경우, 핵심 엔진 수정 없이 템플릿 추가만으로 동작해야 함 | High |
| **NF-03** | API 예외 처리 | 네트워크 지연, API 호출 한도 초과(Rate Limit) 등에 대비한 재시도(Retry) 및 예외 처리 로직 구현 | Medium |

## 4. 기술 스택 (Tech Stack)

- **Core Languages:** `Python 3.10+` (Main Engine & Automation), `Rust` (Target Language), `C` (Source Language)
- **Transpiler & Build Tools:** `C2Rust`, `Cargo`
- **LLM APIs:** `OpenAI API (GPT-4o)` or `Google Gemini API`
- **Environment:** `Linux/Ubuntu` or `WSL2` (C2Rust 호환성 및 파이프라인 구동용)

## 5. 단계별 개발 마일스톤 (3개월 / 약 12주 계획)

- $$$$
    
    **Month 1 (1~4주차): 메인 파이프라인 MVP 구축**
    
    - C2Rust 설치 및 로컬 변환 환경 세팅
    - $$Main Engine$$
        
        C 코드 로드 -> C2Rust 실행 -> LLM API 호출 -> 결과물 저장에 이르는 기본 파이썬 컨트롤러 스크립트 작성
        
    - 소규모 C 코드 대상 기초 변환 테스트 및 API 연동 안정성 확보
- $$$$
    
    **Month 2 (5~8주차): 영문 Insight Prompting 및 피드백 루프 구현**
    
    - CRUST-bench 데이터셋을 활용하여 `unsafe` 발생 주요 실패 패턴 수동 분석
    - 분석 결과를 바탕으로 최적화된 영문 Insight Prompt 작성 및 Prompt Generator 모듈 연동
    - 컴파일 에러 발생 시 로그를 파싱하여 LLM에 재요청하는 Auto-Repair (Feedback) Loop 통합
- $$$$
    
    **Month 3 (9~12주차): 대규모 검증 및 최종 고도화**
    
    - 배치(Batch) 처리 스크립트 작성을 통한 대량의 파일 변환 자동화
    - Syzygy_Zopfli 등 실무 복잡도 코드 대상 일반화 성능 검증 (컴파일 성공률 및 `unsafe` 감소율 정량 평가)
    - 파이프라인 코드 리팩토링, 사용자 친화적 출력 포맷 적용 및 최종 결과보고서 작성

## 6. 최종 배포 및 활용 계획 (Deployment Plan)

- 본 프로젝트는 누구나 쉽게 C-to-Rust 변환 파이프라인을 사용할 수 있도록 **Docker 기반의 배포 환경**을 제공할 예정입니다.
    - **격리된 환경 제공:** 사용자는 로컬 환경에 C2Rust, Rust Toolchain, Python 등을 복잡하게 직접 설치할 필요가 없습니다.
    - **공식 Docker 이미지 배포 (Public Registry):** 최종 완성된 파이프라인 엔진은 Docker Hub 또는 GitHub Container Registry(GHCR)에 퍼블릭 이미지로 등록 및 배포됩니다. 사용자는 소스 코드를 클론하여 직접 빌드할 필요 없이, `docker pull` 명령어 한 번으로 즉시 최신 버전의 엔진을 내려받을 수 있습니다.
    - **원클릭 실행:** 사용자는 제공되는 실행 명령어(`docker run ...`)에 변환할 C 소스 코드의 경로만 넘겨주면, 컨테이너 내부에서 변환 파이프라인이 즉시 가동되어 안전하게 변환된 최종 `.rs` 파일만 사용자에게 반환됩니다.

# [Part 2] 핵심 구현 전략: 인간 통찰력 기반 프롬프트 엔진 (Core Backbone)

> 프로젝트의 독창적인 본질(Core Contribution)인 '통찰력 기반 프롬프팅 및 피드백 기술'의 구현 명세입니다.
> 

## 2.1. 관용적 안전 코드로의 승격 (Idiomatic Translation Engine)

> 💡 **Core Idea:** *NDSS User Study (Translating C To Rust: Lessons from a User Study)* 논문에서 관찰된 **인간 개발자의 변환 전략**을 LLM 시스템 프롬프트로 규격화합니다.
> 

C2Rust를 통해 1차 변환된 `unsafe` 코드를 입력받은 프롬프트 엔진은 다음의 핵심 규칙(Human Insight)을 LLM에 주입합니다.

- **Semantic Lifting 적용:** 기계적으로 변환된 Raw Pointer(`mut T`) 문맥을 파악하여 고수준 타입(`Vec<T>`, `String`, 슬라이스 `&[T]`)으로 의미적 승격을 강제.
- **Borrow Checker 해결 전략 (Cloning & Elision):** 소유권 충돌이 예상되는 다중 참조 상황에서, 인간이 취하는 방식인 `.clone()`을 통한 데이터 복제나 이터레이터(Iterator)를 활용한 포인터 생략 기법을 지시.
- **Zero Unsafe:** 최종 출력물에서 `unsafe` 블록을 100% 제거하도록 강제.

## 2.2. 컴파일 피드백 루프 (Few-Shot Guided Auto-Repair)

> 💡 **Core Idea:** *SafeTrans (Few-shot guided repair)* 전략을 차용하여, LLM의 구문 오류를 바로잡는 피드백 루틴.
> 

단순 에러 로그만 넘기는 방식은 복구율이 현저히 낮습니다. 프롬프트 엔진은 **에러 코드 맞춤형 Few-shot 가이드**를 동적으로 주입하여 수정을 유도합니다.

- **피드백 매핑 예시:**
    - **`E0382 (Use of moved value)`:** "소유권이 이동되었습니다. 타입이 Clone을 지원한다면 `.clone()`을 사용하거나, 소유권 이동 대신 참조(`&` 또는 `&mut`)를 전달하도록 함수 시그니처를 수정하세요. [Few-shot 예제 코드 제공]"
    - **`E0133 (Use of unsafe code)`:** "안전한 함수 내에서 unsafe 연산이 발생했습니다. Raw 포인터 역참조를 안전한 슬라이스 인덱싱이나 이터레이터로 대체하세요. [Few-shot 예제 코드 제공]"

# [Part 3] 파이프라인 고도화 및 평가 전략 (Performance Enhancements & SOTA Integrations)

> Part 2의 순수 프롬프트 엔진만으로 해결하기 어려운 한계(타입 추론 실패, 프로젝트 단위 문맥 소실)를 극복하기 위해, 타 SOTA 논문의 기법을 **보조/성능 고도화 모듈**로 결합하는 전략입니다. 이 모듈들의 On/Off를 통해 프롬프트 엔진 본연의 성능 향상폭(Ablation Study)을 증명할 수 있습니다.
> 

## 3.1. DFG 분석을 통한 타입 추론 보조 모듈 (Pre-processing)

> 💡 **적용 논문:** *Optimizing Type Migration (DFG Approach)*
> 

순수 LLM이 긴 코드에서 포인터의 의도를 놓치는 것을 방지하기 위해, 파이프라인의 극초반에 **데이터 흐름 그래프(DFG)** 분석 개념을 도입합니다.

- **Type & Enum Migration 보조:** 프롬프트 엔진이 변환을 지시하기 전, 코드를 1차 스캔하여 다중 대여(Multiple Borrowing) 변수나 스칼라/배열 포인터의 의도를 사전 마킹(JSON 형태)하여 LLM의 프롬프트 컨텍스트로 추가 주입합니다.

## 3.2. 대규모 프로젝트 변환 모듈 (Skeleton-Guided Divide & Conquer)

> 💡 **적용 논문:** *EvoC2Rust (Skeleton-guided Framework)*
> 

수천 줄의 코드나 다수의 함수가 포함된 파일 변환 시 발생하는 LLM 컨텍스트 한계 초과를 해결하기 위한 '뼈대 분할' 파이프라인 확장입니다.

1. **Skeleton Extraction (뼈대 추출):** 파이썬 파서를 통해 C 코드에서 매크로, 전역 변수, 구조체, 함수 시그니처만 추출하여 '컴파일 가능한 Rust 뼈대(Global Context)'를 구축.
2. **Function-level Translation:** 프롬프트 엔진에게 `[Global Context 뼈대] + [Target Function 1개]` 단위로 묶어 반복적으로 분할 변환을 지시.

## 3.3. FFI 기반 End-to-End 정밀 검증 모듈

> 💡 **적용 논문:** *SACTOR (FFI Verification)* & *SafeTrans (Vulnerability Mitigation)*
> 

프롬프트 엔진이 만들어낸 코드가 문법적으로 컴파일되는 것을 넘어, '진짜 원본 C와 똑같이 동작하는지' 입증하는 하드코어 검증 환경입니다.

- **FFI 테스트 자동화:** 변환된 Rust 코드를 FFI를 통해 원본 C 테스트 스위트에 임베딩하여, 원본의 입력값에 대한 출력값이 100% 일치하는지(Semantic Equivalence) 교차 검증합니다.
- **보안 취약점 완화 검증:** 원본 C 코드의 오버플로우 유발 입력을 주입했을 때, Rust 코드가 메모리 오염 없이 안전하게 패닉(Panic) 방어해 내는지 입증합니다.

## 3.4. 결과 시각화 대시보드 (UI / Frontend)

단순 CLI 출력을 넘어, 변환 결과와 성능 지표를 직관적으로 확인할 수 있는 Python 기반 가벼운 웹 대시보드(Streamlit)를 구축합니다.

- **Metrics Dashboard:** 코드 라인 수 변화, `unsafe` 블록 감소율, 토큰 소모량(비용 최적화 모니터링), 컴파일 통과 여부 시각화.
- **Code Diff Viewer:** 원본 `unsafe` 코드(좌)와 Oxidizer가 정제한 `Safe Rust` 코드(우)의 변경점 하이라이트 표시.

# [Part 4] 향후 확장 로드맵 (Future Work)

> Oxidizer 프레임워크의 완전성과 학술적 가치를 극대화하기 위해, 프로젝트 후반부 또는 향후 연구 과제로 도입을 고려할 최전선(SOTA) 기술들입니다.
> 

### 4.1. RAG 기반 자가 진화형 지식 검색 (Self-Evolving Knowledge Retrieval)

> 💡 **참고 논문:** *His2Trans (Historical Retrieval)* & *IRENE (Rule-augmented Retrieval)*
> 
- **한계 인식:** 컴파일 에러 피드백을 수동 매핑(Rule-based)하는 방식은 예상치 못한 복잡한 에러나 엣지 케이스에 취약합니다.
- **도입 계획:** 과거 성공적으로 변환되었거나 컴파일 에러를 수정한 이력(Historical traces)을 벡터 데이터베이스(Vector DB)에 저장합니다. 에러 복구 시 **RAG(Retrieval-Augmented Generation)** 기법을 활용하여, LLM이 과거의 성공 패턴을 동적으로 검색해오도록 프롬프트 엔진을 자가 진화형으로 고도화합니다.

### 4.2. AST 기반 미세 분할 (Fine-grained Slicing) 및 문맥 주입

> 💡 **참고 논문:** *C2SAFERRUST (NeuroSymbolic Techniques)*
> 
- **한계 인식:** 함수 단위 분할(Function-level)만으로는 수백 줄 이상의 거대 함수를 처리할 때 여전히 환각이 발생합니다.
- **도입 계획:** 파이썬 추상 구문 트리(AST) 파서를 활용해 거대한 함수를 블록(Block) 단위의 '슬라이스(Slice)'로 미세 분할합니다. 변환 시 해당 함수의 **호출부(Call-sites)**와 **Imports** 정보를 프롬프트에 강제 주입하여 타입 불일치를 원천 차단합니다.

### 4.3. 빌드 시스템 추적 (Build Tracing) 기반 의존성 해결

> 💡 **참고 논문:** *His2Trans (Build-aware Skeleton)*
> 
- **한계 인식:** 실무 C 프로젝트는 복잡한 `Makefile`로 구성되어 있어 정규식 파싱으로는 매크로 의존성(Dependency Hell)을 추적하기 어렵습니다.
- **도입 계획:** 변환 시작 전 `compile_commands.json`을 추적(Build Tracing)하여 프로젝트의 실제 빌드 컨텍스트를 파악한 뒤, 결정론적인(Deterministic) 프로젝트 레벨 뼈대를 생성하는 모듈을 도입합니다.

### 4.4. 구조화된 의미 요약 (Structured Summarization) 도입

> 💡 **참고 논문:** *IRENE (Integrating Rules and Semantics)*
> 
- **한계 인식:** 복잡한 로직을 가진 C 코드의 경우 LLM이 즉시 번역에 돌입하면 전체적인 논리적 의미(Semantics)를 오역하는 경우가 발생합니다.
- **도입 계획:** 번역 전 LLM에게 "이 함수의 목적과 주요 로직을 구조화된 형태(Structured Summary)로 먼저 설명하라"고 지시하여, Chain-of-Thought 기법의 시맨틱 이해도를 극대화하는 안전장치를 추가합니다.
