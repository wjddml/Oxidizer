🏗️ Oxidizer 시스템 아키텍처 및 엔지니어링 리포트

본 문서는 Oxidizer 프레임워크의 내부 구조, 설계 철학, 모듈별 역할, 그리고 개발 과정에서 직면한 엔지니어링 과제와 해결 방법을 다루는 기술 문서입니다. 웹 인터페이스 연동, 인프라 고도화 및 시스템 유지보수를 담당하는 개발자와 캡스톤 평가자를 대상으로 작성되었습니다.

1. 시스템 정체성: 프레임워크와 에이전트의 결합

Oxidizer는 단순한 프롬프트 스크립트를 넘어, 두 가지 핵심 정체성을 결합한 하이브리드 시스템으로 설계되었습니다.

제어 가능한 프레임워크 (Controllable Framework): LLM의 비결정론적(Non-deterministic) 출력을 제어하기 위해 정적 분석(AST, DFG), 기능 레퍼런스(C2Rust), 모범 사례 검색(RAG) 파이프라인을 구축했습니다. 각 단계는 독립된 모듈로 동작하여 필요에 따라 교체나 확장이 용이한 프레임워크를 제공합니다.

자율형 에이전트 (Autonomous Agent): LLM이 코드를 1차 생성하는 데 그치지 않고, RepairAgent가 격리된 샌드박스에서 컴파일러와 직접 상호작용합니다. 에러를 분석하고 LLM에게 재수정을 지시하는 자율적 피드백 루프를 가동합니다.

2. 핵심 구성 요소 및 디렉토리 아키텍처

시스템은 '관심사 분리(Separation of Concerns)' 원칙에 따라 디렉토리와 클래스로 철저히 모듈화되어 있습니다.

🧠 src/agent/ (사령탑 및 복구 에이전트)

Orchestrator: 6단계 파이프라인의 전체 데이터 흐름을 통제하는 메인 엔진입니다. 서브 모듈 간의 의존성을 주입하고, 터미널 UI 렌더링 타이밍 등을 총괄 관리합니다.

RepairAgent: 컴파일 에러 복구를 전담합니다. 샌드박스 구축, rustc 에러 로그 파싱, 소스코드 백업/롤백, 그리고 에러 맞춤형 프롬프트 조립을 수행합니다.

📝 src/prompter/ (컨텍스트 조립 및 규칙 관리) - 📌 핵심 모듈화 지점

본 시스템의 주요 설계 특징 중 하나는 '변환 규칙(Rules)'과 '동작 엔진(Engine)'의 물리적 분리입니다.

PromptBuilder: 하드코딩된 프롬프트를 지양하고, prompts/rules/ 디렉토리에 정의된 독립적인 YAML/텍스트 파일들(예: 메모리 관리, 포인터 규칙)을 런타임에 읽어 들여 시스템 프롬프트를 조립합니다. 이를 통해 파이썬 핵심 로직을 수정하지 않고도 새로운 변환 규칙을 자유롭게 추가 및 확장할 수 있습니다.

RagRetriever: 추출된 C 코드의 특징을 바탕으로 data/examples의 벡터 데이터베이스에서 가장 적합한 Safe Rust 변환 사례를 검색해 동적인 컨텍스트를 구성합니다.

🔍 src/analyzer/ (정적 분석 엔진)

SkeletonGenerator: AST(추상 구문 트리) 파서를 활용해 C 소스 코드에서 함수 시그니처와 구조체 선언부만 추출하여 LLM에게 전역적 문맥(Global Context)을 제공합니다.

CSemanticExtractor: 포인터의 실제 사용 의도를 데이터 흐름 그래프(DFG) 기반으로 추론하여 의미론적 지문(Semantic Fingerprint)을 생성합니다.

🔌 src/llm/ (다중 모델 통신 레이어)

BaseLLMClient & LLMFactory: 팩토리 패턴(Factory Pattern)과 추상화 인터페이스를 적용했습니다. 메인 파이프라인은 구체적인 벤더(OpenAI, Anthropic, Google)를 알 필요 없이 generate() 메서드만 호출합니다. 향후 새로운 LLM이 등장하더라도 클라이언트 클래스 하나만 추가하면 즉시 연동됩니다.

🛠️ src/utils/ (인프라 및 유틸리티)

ui_renderer.py: rich 라이브러리를 도입하여 프로그레스 바 애니메이션과 성능 지표 대시보드를 렌더링합니다.

logger.py: 전역 싱글톤 로거입니다. 콘솔(INFO)과 파일(DEBUG) 출력을 이원화하여 UI 깨짐을 방지하고 상세한 디버깅 트레이스 로그(logs/oxidizer_debug.log)를 남깁니다.

workspace_manager.py: 파일 I/O 및 Cargo 샌드박스 상태를 관리하여 프로세스 간 파일 충돌을 방지합니다.

3. 주요 엔지니어링 문제 해결 (Troubleshooting)

개발 과정에서 직면한 엔지니어링 한계와 이를 소프트웨어 공학적으로 해결한 과정입니다.

🚨 이슈 1: LLM의 마크다운 포맷팅 일탈 (Parsing Anomalies)

문제: LLM이 코드 블록(백틱)을 누락하거나, 코드 블록 외부에 불필요한 설명을 덧붙여 파싱 오류 및 컴파일 실패를 유발하는 현상.

해결 (Regex & Fallback Strategy): 추출 로직(_parse_llm_response)에 다중 방어막을 구축했습니다. 정규식을 유연하게 설정하여 공백 및 줄바꿈 오차를 허용하고, 정규식 매칭 실패 시 마커 이후의 텍스트를 강제 추출하여 문자열 양끝의 마크다운 찌꺼기를 도려내는 정교한 Fallback 필터를 구현했습니다.

🚨 이슈 2: API Rate Limit 및 응답 누락 처리

문제: 복구 루프(Auto-Repair)에서 단기간에 LLM API를 다수 호출 시, 할당량 제한(HTTP 429)에 걸리거나 빈 문자열이 반환되어 파이프라인이 중단되는 현상.

해결 (Graceful Rollback): LLM 응답이 유효하지 않음을 감지할 경우 예외를 발생시켜 시스템을 종료하는 대신, WorkspaceManager.rollback_file()을 호출하여 망가진 코드를 컴파일 이전의 안전한 상태로 복구한 뒤 루프를 종료하거나 대기하도록 처리했습니다.

🚨 이슈 3: Cargo 샌드박스의 상태 오염 (State Contamination)

문제: 반복적인 수리 루프 과정에서 이전 시도의 더미 파일이나 캐시가 다음 컴파일에 영향을 주어 원인 불명의 에러가 발생하는 문제.

해결 (Isolated Workspace): WorkspaceManager가 매 실행 시 독립된 Cargo 프로젝트를 초기화하고, 수리 시도마다 철저한 백업 파일(.old)을 생성하여 언제든 오염되지 않은 클린 룸(Clean-room) 상태로 롤백할 수 있는 환경을 보장했습니다.

4. 확장성 및 향후 연동 고려사항 (Extensibility & Future Work)

현재 시스템은 명확하게 모듈화되어 있어, 타 팀 및 기여자들의 확장이 용이합니다.

도메인 특화 규칙 확장 (Rule Extensibility):

보안 전문가나 도메인 지식 전문가는 파이썬 코드를 알 필요가 없습니다. 특정 임베디드 환경이나 커널 종속적인 C 코드 변환 규칙을 prompts/rules/ 폴더에 문서(YAML/JSON)로 추가하기만 하면, 프레임워크가 이를 즉시 학습하고 변환에 반영합니다.

웹 프론트엔드 연동 (Web UI Integration):

현재의 CLI 진입점(main.py) 대신, FastAPI/Flask 등을 활용해 API 래퍼(Wrapper)를 구축하기 쉬운 구조입니다. 파이프라인 종료 후 수집되는 MetricsCollector의 딕셔너리 데이터를 JSON으로 반환받아 웹 브라우저 상에 대시보드를 렌더링할 수 있습니다.

병렬 처리 지원 (Parallel Execution):

현재의 대량 변환(batch)은 순차적으로 실행됩니다. 향후 WorkspaceManager가 샌드박스 생성 시 고유한 UUID를 부여하도록 수정하여 파일 시스템 충돌을 방지하면, 멀티프로세싱을 통한 대규모 병렬 변환이 가능해집니다.