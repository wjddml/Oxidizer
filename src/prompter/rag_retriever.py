# src/prompter/rag_retriever.py
import json
from pathlib import Path
from typing import Dict, List, Any
import chromadb
from chromadb.utils import embedding_functions

class RagRetriever:
    """
    RAG 엔진: 오직 '과거의 성공적인 Safe Rust 변환 예시 코드(Idioms)'만을 관리하고 검색합니다.
    (5대 인간 변환 규칙은 PromptBuilder에서 정적으로 처리됩니다.)
    """
    def __init__(self, db_path: str = "./data/cache/vector_db"):
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        self.collection = self.client.get_or_create_collection(
            name="rust_examples",
            embedding_function=self.embedding_fn
        )

    def seed_database(self, examples_dir: Path):
        """
        data/examples 디렉토리의 JSON/YAML 파일들에서 Safe Rust 코드 예시를 적재합니다.
        (예시 포맷: {"intent": "배열 순회 포인터 연산", "code": "for (i, v) in arr.iter().enumerate() {}"})
        """
        if not examples_dir.exists():
            print(f"⚠️ [RAG] 예시 코드가 있는 '{examples_dir}' 폴더가 없습니다. RAG 적재를 건너뜁니다.")
            return

        print(f"🌱 [RAG] '{examples_dir}'에서 Safe Rust 변환 예시를 벡터 DB에 적재 중...")
        existing_ids = self.collection.get()["ids"] if self.collection.count() > 0 else []
        
        ids_to_add, documents_to_add, metadatas_to_add = [], [], []
        
        # .json 파일 형태의 예시 데이터베이스를 가정
        for file_path in examples_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    examples = json.load(f)
                    
                for i, ex in enumerate(examples):
                    ex_id = f"{file_path.stem}_ex_{i}"
                    if ex_id not in existing_ids:
                        ids_to_add.append(ex_id)
                        # 특징(Intent)을 문서(검색 기준)로 사용
                        documents_to_add.append(ex.get("intent", ""))
                        # 실제 코드는 메타데이터로 숨김
                        metadatas_to_add.append({"snippet": ex.get("code", "")})
            except Exception as e:
                print(f"⚠️ [Warning] {file_path.name} 예시 로드 실패: {e}")
                
        if ids_to_add:
            self.collection.add(
                documents=documents_to_add,
                metadatas=metadatas_to_add,
                ids=ids_to_add
            )
            print(f"✅ [RAG] {len(ids_to_add)}개의 신규 변환 예시 적재 완료.")

    def retrieve_examples(self, semantic_fingerprints: Dict[str, Any], top_k: int = 2) -> List[str]:
        """
        의미론적 지문을 바탕으로 가장 유사한 패턴의 과거 변환 예시 코드를 검색합니다.
        """
        if not semantic_fingerprints or "fingerprints" not in semantic_fingerprints:
            return []
            
        print("🔎 [RAG] C DFG 지문을 바탕으로 가장 유사한 Safe Rust 예시 코드 검색 중...")
        queries = []
        for var, data in semantic_fingerprints["fingerprints"].items():
            features = [data.get("type", "")]
            if data.get("is_array"): features.append("array pointer access")
            if data.get("is_iterator"): features.append("pointer arithmetic iteration")
            queries.append(" ".join(features))
                
        if not queries:
            return []

        results = self.collection.query(
            query_texts=queries,
            n_results=min(top_k, self.collection.count())
        )
        
        retrieved_snippets = set()
        if results and "metadatas" in results:
            for metadata_list in results["metadatas"]:
                for metadata in metadata_list:
                    retrieved_snippets.add(metadata.get("snippet", ""))
                    
        return list(retrieved_snippets)

    def format_for_prompt(self, snippets: List[str]) -> str:
        """검색된 예시 코드를 프롬프트 포맷으로 변환합니다."""
        if not snippets:
            return ""
        
        lines = []
        for i, snippet in enumerate(snippets, 1):
            lines.append(f"**Example {i}:**\n```rust\n{snippet}\n```")
        return "\n".join(lines)