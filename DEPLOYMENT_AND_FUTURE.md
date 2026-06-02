🚀 Oxidizer 배포 가이드 및 향후 로드맵 (Deployment & Future Roadmap)

본 문서는 Oxidizer 프레임워크를 안정적인 컨테이너 환경으로 배포하기 위한 시스템 구축 가이드와, 향후 학술적 가치 및 상용성을 높이기 위한 연구/개발 로드맵을 정의합니다. 배포(Infrastructure)를 담당하는 엔지니어 및 프로젝트의 비전을 검토하는 평가자를 대상으로 작성되었습니다.

1. 배포 시스템 구축 가이드 (Deployment Guide)

Oxidizer는 파이썬(LLM 제어 및 파싱), Rust 툴체인(Cargo 빌드), 그리고 C 컴파일러(C2Rust 및 파서 의존성)라는 복잡한 다중 언어 환경을 요구합니다. 따라서 OS 파편화 문제를 원천 차단하기 위해 Docker 기반의 컨테이너화 배포를 강력히 권장합니다.

1.1. Dockerfile 설계 권장안 (Draft)

Ubuntu 22.04 LTS를 베이스 이미지로 사용하여 필수 시스템 패키지와 툴체인을 구성하는 권장 구조입니다.

# 1. Base Image
FROM ubuntu:22.04

# 2. System Dependencies (C Compiler, LLVM, Clang, Python)
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    build-essential \
    llvm clang libclang-dev \
    python3 python3-pip python3-venv \
    curl git cmake \
    && rm -rf /var/lib/apt/lists/*

# 3. Rust Toolchain Setup
RUN curl --proto '=https' --tlsv1.2 -sSf [https://sh.rustup.rs](https://sh.rustup.rs) | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# 4. Install C2Rust (정적 변환기)
RUN cargo install c2rust

# 5. Application Setup
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 6. Copy Source Code
COPY . .

# 7. Default Entrypoint (명령어 오버라이딩 지원)
ENTRYPOINT ["python3", "src/main.py"]
CMD ["--help"]


1.2. API 키 및 보안 관리 (Security Considerations)

API 키 하드코딩 절대 금지: LLM API 키(OpenAI, Anthropic, Gemini)는 절대 컨테이너 이미지 내부나 코드 깃허브 저장소에 포함되어서는 안 됩니다.

환경 변수 주입 (Env Vars): 배포 환경(예: Docker Compose, Kubernetes, AWS ECS)에서 런타임에 .env 파일을 마운트하거나 시스템 환경 변수로 주입해야 합니다.

# 안전한 Docker 실행 예시
docker run --rm -v $(pwd)/inputs:/app/inputs -v $(pwd)/outputs:/app/outputs --env-file .env oxidizer-agent batch /app/inputs


2. 향후 연구 및 기능 확장 로드맵 (Future Work)

현재 완성된 파이프라인 엔진을 기반으로, 성능과 안정성을 '상용 소프트웨어' 수준으로 끌어올리기 위한 추가 과제 후보입니다.

🎯 단기 로드맵 (Short-term)

동작 동등성 자동 검증 모듈 (Functional Equivalence Testing)

개요: 변환된 Rust 코드가 컴파일되는 것을 넘어, "C 프로그램과 완벽히 동일하게 동작하는가?"를 증명하는 블랙박스 I/O 테스팅입니다.

구현 방안: 원본 C 실행 파일과 최종 Rust 실행 파일에 동일한 CLI 인자나 표준 입력(stdin)을 주입하고, 반환되는 표준 출력(stdout), 에러 출력(stderr), 종료 코드(Exit Code)가 100% 일치하는지 파이썬 subprocess로 자동 대조하는 평가(eval) 서브 커맨드를 완성합니다.

API 할당량 방어 시스템 (Exponential Backoff)

개요: LLM의 토큰 제한(Rate Limit, HTTP 429 Error)으로 인해 파이프라인이 중단되는 것을 방지합니다.

구현 방안: LLMClient 네트워크 통신 레이어에 지수적 백오프(Exponential Backoff) 로직을 탑재하여, 에러 발생 시 시스템이 즉사하지 않고 자율적으로 N초간 대기(Sleep) 후 재시도하도록 안정성을 강화합니다.

🚀 중장기 로드맵 (Long-term & Academic Research)

자가 진화형 지식 검색 (Self-Evolving RAG Retrieval)

개요: 현재의 RAG는 정적인 예시 데이터를 사용하지만, 에이전트가 스스로 학습하도록 고도화합니다.

구현 방안: RepairAgent가 컴파일 에러를 해결하고 복구에 성공할 때마다, 해당 '에러 로그 ➡️ 수정된 코드'의 쌍(Historical Traces)을 벡터 DB(ChromaDB)에 새로운 예시로 자동 저장합니다. 시스템이 많이 사용될수록 복구 능력이 스스로 진화하게 됩니다.

보안성 극대화를 위한 C 정적 분석기 연동 (Pre-Vulnerability Scanning)

개요: 레거시 C 코드에 이미 존재하는 버퍼 오버플로우나 메모리 누수 취약점을 사전에 파악하여 완벽하게 방어하는 코드를 짜도록 유도합니다.

구현 방안: 파이프라인 극초반에 Clang Static Analyzer를 가동하여 취약점 리포트를 생성하고, 이를 LLM의 프롬프트에 주입하여 *"해당 보안 약점이 Safe Rust의 타입 시스템으로 원천 차단되도록 설계하라"*고 명시적으로 지시합니다.

3. 연구 및 평가 데이터셋 (Evaluation Datasets)

향후 Oxidizer의 성능 향상을 객관적으로 측정하고 논문 등 학술 자료로 증명하기 위해, 점진적인 난이도를 가진 3개의 트랙(Track)으로 데이터셋을 구성하여 벤치마크를 수행할 예정입니다.

구분

데이터셋

활용 목적 및 계획

Track 1 (기초/패턴)

CRUST-bench

C-to-Rust 변환 연구를 위해 함수 단위로 정제된 소규모 벤치마크. 초기 통찰력 프롬프트 설계, unsafe 블록 발생 원인 정밀 분석, 파이프라인 MVP 동작 및 에러 복구율(Repair Rate) 측정용으로 사용합니다.

Track 2 (표준/I.O)

simcrat

GNU Coreutils 등을 포함한 벤치마크. C 표준 라이브러리(libc) 및 시스템 파일 I/O API가 Rust 표준 라이브러리(std)로 올바르게 매핑 및 승격(Lifting)되는지 중점적으로 평가합니다.

Track 3 (심화/실무)

Syzygy_Zopfli

구글의 압축 알고리즘 구현체. 복잡한 비트 연산과 포인터 산술 연산이 포함된 실무 레벨 코드로, 제안하는 에이전트의 최종 일반화 성능 및 I/O 동등성을 증명하는 '최종 테스트베드' 격으로 활용합니다.