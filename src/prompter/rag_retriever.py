# src/prompter/rag_retriever.py
import yaml
from pathlib import Path
from typing import Dict, List, Any
import chromadb
from chromadb.utils import embedding_functions

class RagRetriever:
    """
    NDSS User Study 기반의 5대 규칙(YAML)을 벡터 DB에 적재하고,
    정적 분석 지문을 바탕으로 최적의 Safe Rust 변환 규칙(처방전)을 검색합니다.
    """
    def __init__(self, db_path: str = "./data/cache/vector_db"):
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # ChromaDB 로컬 영구 저장소 초기화
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        
        # 문장 임베딩 모델 (코드 및 자연어 의미 분석용)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        self.collection = self.client.get_or_create_collection(
            name="rust_idioms",
            embedding_function=self.embedding_fn
        )

    def seed_database(self, rules_dir: Path):
        """
        prompts/rules 디렉토리의 YAML 파일들을 파싱하여 벡터 DB에 적재합니다.
        """
        print(f"🌱 [RAG] '{rules_dir}'에서 Safe Rust 변환 규칙을 벡터 DB에 적재 중...")
        
        existing_ids = self.collection.get()["ids"] if self.collection.count() > 0 else []
        
        ids_to_add = []
        documents_to_add = []
        metadatas_to_add = []
        
        for yaml_file in rules_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    rules_data = yaml.safe_load(f)
                    
                # 마스터의 YAML 포맷 (rules: 리스트 구조) 처리
                if rules_data and "rules" in rules_data:
                    for i, rule in enumerate(rules_data["rules"]):
                        rule_id = f"{yaml_file.stem}_rule_{i}"
                        
                        if rule_id not in existing_ids:
                            ids_to_add.append(rule_id)
                            
                            # [핵심] 'name'과 'trigger' 키워드들을 합쳐서 검색(Embedding)의 대상으로 삼습니다.
                            triggers = " ".join(rule.get("trigger", []))
                            intent_text = f"{rule.get('name', '')} {triggers}"
                            documents_to_add.append(intent_text)
                            
                            # 실제 프롬프트에 주입할 처방전은 'description'입니다.
                            metadatas_to_add.append({
                                "rule_name": rule.get("name", "Unknown Rule"),
                                "rule_content": rule.get("description", "")
                            })
                            
            except Exception as e:
                print(f"⚠️ [Warning] {yaml_file.name} 파싱 실패: {e}")
                
        if ids_to_add:
            self.collection.add(
                documents=documents_to_add,
                metadatas=metadatas_to_add,
                ids=ids_to_add
            )
            print(f"✅ [RAG] {len(ids_to_add)}개의 신규 규칙 적재 완료.")

    def retrieve_rules(self, semantic_fingerprints: Dict[str, Any], top_k: int = 3) -> List[Dict[str, str]]:
        """
        추출된 의미론적 지문(C DFG 등)을 Query로 변환하여 관련 규칙을 검색합니다.
        """
        if not semantic_fingerprints or "fingerprints" not in semantic_fingerprints:
            return []
            
        print("🔎 [RAG] 의미론적 지문을 바탕으로 최적의 Safe Rust 패턴 검색 중...")
        
        queries = []
        for var, data in semantic_fingerprints["fingerprints"].items():
            # 추출된 특징(Array, Iterator, Allocated)과 C 변수 타입을 검색 쿼리로 사용
            features = [data.get("type", "")]
            if data.get("is_array"): features.append("array bounds pointer")
            if data.get("is_iterator"): features.append("pointer arithmetic offset")
            if data.get("is_allocated"): features.append("malloc memory")
            
            queries.append(" ".join(features))
                
        if not queries:
            return []

        # 쿼리들을 이용해 ChromaDB 벡터 검색 수행
        results = self.collection.query(
            query_texts=queries,
            n_results=min(top_k, self.collection.count())
        )
        
        # 중복 규칙 제거를 위한 Set 활용
        retrieved_rules_map = {}
        if results and "metadatas" in results:
            for metadata_list in results["metadatas"]:
                for metadata in metadata_list:
                    rule_name = metadata.get("rule_name")
                    if rule_name not in retrieved_rules_map:
                        retrieved_rules_map[rule_name] = metadata.get("rule_content")
                        
        return [{"name": k, "description": v} for k, v in retrieved_rules_map.items()]

    def format_for_prompt(self, rules: List[Dict[str, str]]) -> str:
        """검색된 규칙들을 LLM 프롬프트용 포맷으로 변환합니다."""
        if not rules:
            return "No specific dynamic rules triggered. Proceed with standard idiomatic Safe Rust practices."
            
        lines = []
        for i, rule in enumerate(rules, 1):
            lines.append(f"{i}. [{rule['name']}]: {rule['description']}")
            
        return "\n".join(lines)