🏗️ Oxidizer 시스템 아키텍처 및 엔지니어링 리포트 (Deep Dive)

본 문서는 Oxidizer 프레임워크의 내부 구동 로직, 세부 파이썬 알고리즘 구현 방식, YAML 기반 통찰력 템플릿의 규칙 구조, 그리고 컴파일 에러 수리 루프의 상태 기계(State Machine)에 관한 정밀 명세서입니다.

1. 정적 분석 및 파이프라인 알고리즘 구현 원리

Oxidizer는 C 코드의 문법과 의미론을 완벽히 통제하기 위해 파이썬 레이어에서 세 가지 정적 분석 알고리즘(Skeleton, Dependency, DFG)을 직접 구현하여 구동합니다.

1.1. AST Skeleton Extraction (SkeletonGenerator)

LLM이 함수의 세부 로직을 번역할 때 매크로나 구조체의 문맥을 잃어 오역하는 현상(Context Loss)을 원천 차단하기 위해, C 소스 코드의 전역 인터페이스 정보만을 가볍게 추출해 내는 모듈입니다.

Tree-sitter AST 탐색 알고리즘:

C 소스 코드를 바이트 스트림으로 변환하여 Tree-sitter C 파서에 주입하고 AST Root Node를 확보합니다.

Root Node의 직계 자식(First-level Children) 노드들을 선형 스캔하며 다음 규칙에 따라 분류합니다:

preproc_def (매크로 정의), struct_specifier (구조체 선언), type_definition (타입 재정의), declaration (전역 변수 선언) 노드는 소스 텍스트를 그대로 보존합니다.

function_definition (함수 정의) 노드를 만나면 내부 AST를 한 단계 더 파고듭니다.

함수 정의 노드 내부에서 function_declarator (함수 시그니처 선언부), primitive_type (반환 자료형) 노드만을 정교하게 추적해 텍스트를 결합한 뒤 끝에 세미콜론 ;을 강제 주입하여 임시 C 함수 원형(Prototype)을 복원합니다.

이를 LLM에 주입하여 Rust 스켈레톤 번역본을 생성할 때, 모든 함수 바디 블록을 공통적으로 { unimplemented!(); } 매크로로 채우도록 지시합니다. 이로써 컴파일 가능하면서도 가벼운 Rust '뼈대 코드'가 완성됩니다.

1.2. Semantic DFG Pointer Extraction (CSemanticExtractor)

C의 포인터(T*)가 실제 Rust에서 참조(&T), 슬라이스(&[T]), 힙 할당 소유권(Box<T>), 동적 배열(Vec<T>) 중 어떤 고수준 타입으로 승격(Semantic Lifting)되어야 하는지 데이터 흐름을 추적하여 판단하는 추론 엔진입니다.

Clang AST 데이터 흐름 추적 및 규칙 알고리즘:

libclang AST 바인딩을 이용하여 타겟 C 함수의 정의부 내부로 탐색 커서(AST Cursor)를 진입시킵니다.

함수 내에서 선언된 파라미터(PARM_DECL) 및 지역 변수(VAR_DECL) 중 타입 철자에 * 또는 [가 포함된 포인터/배열 변수 목록을 메모리 스택에 적재합니다.

추출된 각 포인터 변수의 식별자(Spelling)를 기준으로, 함수 전체 구문 트리를 선행 순회(Pre-order Traversal)하며 해당 변수가 피연산자로 사용되는 모든 노드의 문맥적 특징을 스캔합니다:

배열 인덱스 접근 스캔: 해당 변수 커서의 부모 노드 타입이 ARRAY_SUBSCRIPT_EXPR (예: ptr[i])인 경우가 존재하면 is_array = True 로 결정합니다.

포인터 산술 연산 스캔: 변수가 UNARY_OPERATOR (예: ptr++, --ptr)의 피연산자로 쓰였거나, BINARY_OPERATOR 내에서 정수와 연산(예: ptr + 1)되는 패턴이 잡히면 is_iterator = True 로 결정합니다.

메모리 할당 수명 스캔: 변수 바인딩 하위에 CALL_EXPR 노드가 존재하고 피호출 함수명이 malloc, calloc, realloc이면 is_allocated = True 로, free 함수에 인자로 주입되면 is_freed = True 로 설정합니다.

수집된 원시 데이터 흐름 지문(Fingerprint)을 바탕으로 파이썬 내부의 의미론 매핑 매트릭스를 구동합니다:

is_allocated 이면서 is_array 이면 ➡️ Vec<T>

is_allocated 이지만 단일 스칼라면 ➡️ Box<T>

할당(malloc)은 없지만 is_iterator 혹은 is_array 이면 ➡️ &[T] (Slice) 또는 &mut [T]

단순 역참조(*ptr)만 발생하면 ➡️ &T (Reference)

1.3. Dependency Resolution & Topological Sorting (DependencyAnalyzer)

다수의 C 파일로 구성된 배치 환경에서 어떤 파일이 먼저 Safe Rust로 안전하게 선언/번역되어야 빌드 에러가 발생하지 않는지 분석하는 빌드 오더 계산 엔진입니다.

DFS 위상 정렬 및 Tarjan SCC 탐지 알고리즘:

프로젝트 소스 트리를 스캔하여 모든 .c, .h 파일들의 상대 경로를 노드(Node) 목록으로 구성합니다.

각 파일 내부의 #include "..." 구문을 전처리 스캔하여 로컬 헤더 포함 관계를 의존성 간선(Directed Edge, A -> B: A가 B를 포함함)으로 연결해 방향 그래프(Directed Graph)를 구축합니다.

Tarjan's Strongly Connected Components (SCC) 알고리즘을 호출하여 상호 참조(Circular Dependency) 루프를 돌고 있는 소스 파일 그룹을 스캔합니다.

각 노드 방문 시 방문 순서(disc_time)와 도달 가능한 최소 방문 순서(low_link)를 기록하며 스택(Stack)을 유지합니다.

순환 참조가 감지되면 해당 컴포넌트 목록을 그룹화하여 사용자에게 경고를 보냄으로써 컴파일 불가능 상태를 사전 차단합니다.

순환 참조가 없는 격리된 그래프 구역에 대해 깊이 우선 탐색(DFS) 기반의 위상 정렬을 실행합니다:

방문 중인 상태(temp_mark)와 완전히 정렬 완료된 상태(visited)를 나누어 백트래킹(Backtracking)을 방지합니다.

의존성이 끝나는 말단 노드(Callee)부터 역순으로 결과 리스트(order)에 추가하여 최하위 헤더/소스 파일이 가장 먼저 변환 테이블에 배치되도록 빌드 경로를 생성합니다.

2. YAML 기반 인간 통찰력(Human-Insight) 프롬프트 규칙 설계

Oxidizer는 LLM의 자유도에만 의존하지 않고, 인간 전문가가 정립한 C-to-Rust 변환 규칙을 YAML 파일로 추적 및 주입하여 출력을 제한합니다. prompts/rules/ 디렉토리에 적재되는 핵심 규칙 파일들의 구조와 내부 설계 규칙입니다.

2.1. 포인터 승격 및 소유권 규칙 규격 (prompts/rules/pointer_lifting.yaml)

C2Rust의 기계적 포인터 변환 결과물인 *mut T 및 *const T를 안전한 Idiomatic Rust 타입으로 변환하는 세부 규칙서입니다.

rule_id: "RULE-01-POINTER-LIFTING"
target_pattern: "Raw pointers (*mut T, *const T) and pointer arithmetic"
human_insights:
  - rule: "Array Pointer to Slice Conversion"
    c_pattern: "void process(int *arr, int len)"
    unsafe_rust_pattern: "fn process(arr: *mut i32, len: i32)"
    idiomatic_safe_rust: "fn process(arr: &[i32])"
    reasoning: "C-style pointer + length arguments must be consolidated into Rust's safe Slice (&[T]) to leverage boundaries check and eradicate buffer overflow vulnerabilities."

  - rule: "Pointer Arithmetic to Iterator Conversion"
    c_pattern: "while(*ptr != '\\0') { ptr++; }"
    unsafe_rust_pattern: "while *ptr != 0 { ptr = ptr.offset(1); }"
    idiomatic_safe_rust: "for &char in slice.iter() { ... }"
    reasoning: "Manual index increments and offsets lead to memory safety violations. Replace index iterations with Rust's natively optimized, safety-checked Iterators."

  - rule: "Dynamic Allocation to Safe Collections"
    c_pattern: "int *buf = (int*)malloc(size * sizeof(int));"
    unsafe_rust_pattern: "let buf: *mut i32 = libc::malloc(...) as *mut i32;"
    idiomatic_safe_rust: "let buf: Vec<i32> = vec![0; size];"
    reasoning: "Explicit malloc/free operations must be migrated to resource-managed Rust collections (Vec<T>, Box<T>) to prevent double-free and memory leaks via RAII."


2.2. Borrow Checker 대응 및 메모리 안전화 규칙 규격 (prompts/rules/borrow_resolver.yaml)

Rust 컴파일의 가장 큰 장벽인 대여 검사기(Borrow Checker)의 충돌 상황을 인간 개발자 수준에서 회피하기 위한 행동 가이드라인 규칙서입니다.

rule_id: "RULE-02-BORROW-RESOLVER"
target_pattern: "Multiple mutable aliases and lifetimes conflicts"
human_insights:
  - constraint: "E0502 - Cant borrow as mutable because it is also borrowed as immutable"
    remedy_strategy: "Scope Minimization & Shadowing"
    action_guideline: |
      If a variable requires both read-only and write-access inside a loop, minimize the lifetime of the immutable reference. 
      You must restrict the read scope by nesting it with block braces `{}` or enforce deep copy using `.clone()` if the data type implements Clone trait.
      
  - constraint: "E0382 - Use of moved value"
    remedy_strategy: "Explicit Cloning & Reference Passing"
    action_guideline: |
      If a value is moved into a helper function and used again later in the caller scope, modify the helper function's signature to take a shared reference (`&T`) instead of owning value (`T`), or append `.clone()` explicitly at the calling site.


3. Auto-Repair Engine 및 적응형 컴파일 피드백 루프 알고리즘

Phase 5를 지배하는 RepairAgent는 단순히 에러 로그를 LLM에 재전달하는 수준을 넘어, 컴파일러의 에러 코드를 분석하여 맞춤형 Few-shot 처방전을 결정론적(Deterministic)으로 구성하는 피드백 루프 알고리즘입니다.

               +----------------------------------------+
               |  Rust Output Target (src/main.rs)      |
               +----------------------------------------+
                                   |
                                   v
                      [Cargo Sandbox: run_check()]
                                   |
             +---------------------+---------------------+
             |                                           |
             v (Cargo build OK)                          v (Cargo build FAIL)
      [Compilation Success]                       [Parse compiler stderr]
             |                                           |
    (Return Target Path)                          (E0382, E0502, etc.)
                                                         |
                                                         v
                                            [Load Error-Remedy Few-shot]
                                                         |
                                                         v
                                              [LLM Repair Generation]
                                                         |
                                                         v
                                            [Write & Backup (.rs.old)]


3.1. 컴파일 에러 파서 및 의미론적 수치화 기법 (ErrorParser)

cargo check를 수행하여 가로챈 stderr 스트림 로그에서 필요한 에러 핵심 메타데이터만 기계적으로 정밀 추출해내는 모듈입니다.

컴파일 에러 정규식 파싱 엔진 로직:

stderr 버퍼의 텍스트 라인들을 읽어 들이며 컴파일 에러 코드 패턴(E[0-9]{4})을 감지합니다.

다음 정규 표현식을 순차 적용하여 핵심 디버그 구조체 데이터를 캡처합니다:

에러 코드 캡처: r"error\[(E\d{4})\]" ➡️ 컴파일러 고유 에러 코드(예: E0502) 확보.

발생 위치 캡처: r"-->\s+(.+?):(\d+):(\d+)" ➡️ 에러 파일 경로, 라인 번호, 컬럼 번호 확보.

주 메시지 캡처: r"error\[E\d{4}\]:\s*(.+)" ➡️ 컴파일러가 제시하는 원인 상세 메시지 캡처.

에러 코드의 심각도와 종류를 분류하여 딕셔너리 구조체로 반환하고, 분석 결과에 따라 맞춤형 Few-shot 가이드맵(Guide Map)을 매핑합니다.

3.2. 에러 코드 매핑 기반 Few-shot 유도 제어 로직

RepairAgent는 파싱된 에러 코드에 맞추어 LLM에게 완전히 다른 주입 프롬프트(Few-shot)를 결합하여 수정을 지시합니다.

에러 맞춤형 프롬프트 분기 알고리즘:

E0382 (Moved Value): "The variable has lost ownership. You must pass a reference (&var) instead of the ownership, or insert .clone() at the call site." [Few-shot 예제 코드 동적 주입]

E0502 (Double Borrow): "Rust restricts aliasing of mutable pointers. Re-architect the block scope to drop the immutable borrow before initiating a mutable borrow, or refactor pointer indexing to safe index offsets." [Few-shot 예제 코드 동적 주입]

E0601 (No Main Function): "The target is meant to be a binary executable but lacks a entrypoint. Wrap the helper structures and logic inside fn main() {} block."

3.3. 파일 트랜잭션, 백업 및 안전 롤백 제어 (WorkspaceManager)

자동 복구 루프가 돌면서 자칫 이전 시도의 올바른 코드까지 덮어쓰거나 오염시키는 현상(State Poisoning)을 해결하기 위한 격리 및 백업 알고리즘입니다.

트랜잭션 세부 루틴:

새로운 복구 시도(Attempt N)에 진입하면 WorkspaceManager.backup_file(target_rs_path)를 호출해 현재 파일의 복사본을 생성하며 확장자를 .rs.old로 임시 보관합니다.

LLM이 수정한 새로운 수정 코드 조각을 target_rs_path에 완전히 덮어씁니다.

CargoRunner.run_check()를 수행하여 컴파일 통과 여부를 검증합니다:

성공 시: 백업 파일(.rs.old)을 영구 삭제하고 루프를 빠져나와 최종 Rust 파일의 패스를 사령탑에 전달합니다.

실패 시: 다음 시도(Attempt N+1)로 넘어가며 백업 파일을 재갱신합니다.

한도 초과 실패 시: 최대 재시도 횟수(예: 5회)를 소진하면 WorkspaceManager.rollback_file()을 호출하여 .rs.old를 오리지널 경로로 다시 복원시켜 빌드가 가능한 이전 세대의 안전한 소스코드로 회귀시킵니다.