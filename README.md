Oxidizer 🦀

Human-Insight Guided C-to-Rust Transpilation Agent Framework

Oxidizer는 레거시 C 소스 코드를 메모리 안전성이 보장된 관용적(Idiomatic) Rust 코드로 자동 변환하는 자율형 AI 에이전트 프레임워크입니다.

기존의 정적 변환기(e.g., C2Rust)가 생성하는 거대한 unsafe 블록의 한계와 순수 LLM이 겪는 대용량 문맥 소실(Context Loss) 문제를 해결하기 위해, 정적 분석 기술과 인간 전문가의 변환 통찰력(Human-Insight)을 결합한 하이브리드 엔진을 제안합니다.

✨ 주요 기능 (Key Features)

End-to-End 자율 변환 파이프라인: 단일 소스 파일뿐만 아니라 디렉토리 단위의 대량 C 파일(batch)을 사람의 개입 없이 일괄 변환합니다.

문맥 인식 정적 분석 (Context-Aware Analysis): Tree-sitter 및 Clang 기반 파서를 활용하여 C 함수의 추상 구문 뼈대(Skeleton)와 포인터 데이터 흐름(DFG) 지문을 사전에 추출합니다.

RAG 기반 동적 지식 주입: 과거의 성공적인 변환 사례(Historical traces)를 벡터 데이터베이스에서 검색하여 모델에 최적의 처방전(Prompt)을 동적으로 제공합니다.

지능형 자동 복구 루프 (Resilient Auto-Repair): 샌드박스 환경에서 rustc 컴파일러의 에러(OS 레벨 및 구문 에러)를 파싱하고, 원인을 분석하여 스스로 코드를 수정하는 피드백 루프를 가동합니다.

다중 LLM 아키텍처 (Model Agnostic): 특정 벤더에 종속되지 않으며, CLI 옵션을 통해 최신 LLM(OpenAI GPT-4o, Anthropic Claude 3.5, Google Gemini 2.5) 간의 자유로운 스위칭을 지원합니다.

실시간 대시보드 및 지표 시각화 (Rich Telemetry): 변환 진행률과 함께 최종 생성물의 안전성 점수(Safety Score), 코드 확장률(LOC Ratio), 수리 소요 횟수 등을 직관적인 터미널 UI로 제공합니다.

⚠️ 현재의 한계 및 범위 (Known Limitations & Scope)

Oxidizer는 현재 파일 및 모듈 단위의 독립적 변환에 고도로 최적화되어 있으며, 다음과 같은 한계점을 가집니다. 향후 릴리즈를 통해 점진적으로 개선될 예정입니다.

복잡한 빌드 시스템 의존성: 수십 개의 Makefile과 복잡하게 얽힌 거대 프로젝트의 매크로 및 전역 의존성을 완벽하게 자동 해결하는 기능은 아직 지원하지 않습니다.

런타임 동작 동등성 검증: 컴파일 통과 및 문법적 안전성은 보장하나, 논리적 의미론(Semantic Equivalence)이 동일하게 동작하는지에 대한 런타임 100% 자동 검증은 별도의 I/O 테스트 케이스가 동반되어야 합니다.

시스템 종속적 동시성 모델 재설계: C의 플랫폼 종속적인 스레딩 로직(예: pthread)을 Rust의 안전한 동시성 모델(Arc<Mutex<T>>)로 완벽하게 자율 재설계하는 것에는 프롬프트 기반 LLM 추론의 한계가 존재합니다.

🏗️ 시스템 아키텍처 (Pipeline Architecture)

Oxidizer의 메인 엔진(Orchestrator)은 총 6개의 독립적인 페이즈로 구성된 파이프라인을 비동기적으로 지휘합니다.

[User Input] C Source Code (.c)
   │
   ▼
[Orchestrator] Oxidizer Main Engine
   │
   ├─► [Phase 1: Skeleton] 파서를 통한 함수 인터페이스 및 전역 구조체 뼈대 추출
   ├─► [Phase 2: Semantic DFG] 포인터 의도 및 데이터 흐름 지문(Fingerprint) 추출
   ├─► [Phase 3: RAG & C2Rust] 유사 Safe Rust 모범 답안 검색 및 C2Rust 참조 코드 생성
   ├─► [Phase 4: LLM Synthesis] 문맥 조립 및 LLM 합성 (구조화된 마크다운 반환)
   ├─► [Phase 5: Auto-Repair] Cargo Sandbox 기반 컴파일 검증 및 자율 수리 루프 (Max N Retries)
   │
   ▼
[Phase 6: Metrics & UI] 성능 지표 추출 (unsafe 제거율 등) 및 Rich 대시보드 렌더링
   │
   └─► [Output] Safe & Idiomatic Rust Code (.rs)


🚀 시작하기 (Getting Started)

1. 시스템 요구사항 (Prerequisites)

원활한 동작을 위해 다음의 시스템 패키지들이 요구됩니다. (운영 환경의 파편화를 막기 위해 Docker 기반 배포 환경을 권장합니다.)

Python 3.10+

Rust Toolchain (cargo, rustc)

C2Rust (cargo install c2rust를 통해 설치)

시스템 C/C++ 컴파일러 (build-essential, llvm, clang)

2. 설치 (Installation)

git clone [https://github.com/your-org/Oxidizer.git](https://github.com/your-org/Oxidizer.git)
cd Oxidizer

# 가상환경 생성 및 의존성 패키지 설치
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt


3. 환경 변수 설정 (Configuration)

다중 LLM 지원을 위해 프로젝트 루트에 .env 파일을 생성하고 발급받은 API 키를 기입합니다.

OPENAI_API_KEY="your-openai-api-key"
ANTHROPIC_API_KEY="your-anthropic-api-key"
GEMINI_API_KEY="your-gemini-api-key"


4. 실행 (Usage)

Oxidizer는 표준화된 서브 커맨드(Sub-commands) CLI를 제공합니다.

단일 파일 변환 모드 (Run)

# 기본 변환 실행 (기본 모델 사용)
python3 src/main.py run test.c

# 특정 LLM 벤더 및 모델 지정 실행
python3 src/main.py run test.c --llm gemini --llm-model gemini-2.5-pro


대량 디렉토리 변환 모드 (Batch)

# data/inputs/ 폴더 내의 지정된 디렉토리 전체 순차 변환
python3 src/main.py batch my_legacy_c_project --llm gpt --llm-model gpt-4o


에블레이션 스터디 모드 (Ablation Study)
특정 아키텍처 모듈의 성능 기여도를 평가하기 위해 각 기능을 개별적으로 비활성화할 수 있습니다.

python3 src/main.py run test.c --disable-rag --disable-repair
