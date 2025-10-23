# query_normalizer.py
import os
import json
import pandas as pd

try:
    import openai
except Exception:
    openai = None


class QueryNormalizer:
    """
    🔠 검색어 정규화 도우미
    - CSV 기반 매핑(user_pattern → canonical_term, synonyms)
    - GPT(OpenAI API) 기반 확장 (향후 Gemma 등으로 교체 가능)
    """

    def __init__(self, csv_path="keyword_mapping.csv", use_ai=True, model="gpt-3.5-turbo"):
        self.csv_path = csv_path
        self.use_ai = use_ai
        self.model = model
        self.mapping_df = self._load_mapping(csv_path)
        self._setup_openai()

    # -------------------------------------
    # 내부 설정
    # -------------------------------------
    def _setup_openai(self):
        """환경 변수에서 API 키 불러오기"""
        if openai is None:
            return
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            openai.api_key = api_key

    def _load_mapping(self, path):
        """CSV 매핑표 로드"""
        if not os.path.exists(path):
            print(f"⚠️ 매핑 CSV 파일이 없습니다: {path}")
            return pd.DataFrame(columns=["user_pattern", "canonical_term", "category", "synonyms", "weight"])

        try:
            df = pd.read_csv(path)
            for col in ["user_pattern", "canonical_term", "category", "synonyms", "weight"]:
                if col not in df.columns:
                    df[col] = None
            print(f"✅ 매핑표 {len(df)}행 로드 완료")
            return df
        except Exception as e:
            print(f"❌ CSV 로드 실패: {e}")
            return pd.DataFrame(columns=["user_pattern", "canonical_term", "category", "synonyms", "weight"])

    # -------------------------------------
    # CSV 매핑 로직
    # -------------------------------------
    def map_with_csv(self, query: str):
        """CSV 기반 매핑 검색"""
        if self.mapping_df.empty:
            return []
        q = str(query).strip().lower()
        terms = []
        for _, row in self.mapping_df.iterrows():
            pattern = str(row.get("user_pattern", "")).lower()
            if not pattern:
                continue
            if pattern in q or q in pattern:
                canonical = str(row.get("canonical_term", "")).strip()
                if canonical:
                    terms.append(canonical)
                synonyms = str(row.get("synonyms", "")).strip()
                if synonyms:
                    for s in synonyms.split("|"):
                        s = s.strip()
                        if s:
                            terms.append(s)
        return sorted(list(set([t for t in terms if t])))

    # -------------------------------------
    # GPT / LLM 기반 매핑
    # -------------------------------------
    def map_with_ai(self, query: str):
        """GPT를 사용한 검색어 확장"""
        if not self.use_ai or openai is None or not hasattr(openai, "ChatCompletion"):
            return []
        prompt = f"""
        사용자가 다음과 같이 검색했습니다: "{query}"
        한국어 학술 데이터베이스 검색에 적합하도록 핵심 키워드 5~8개를 생성하세요.
        불용어 제거, 동의어와 관련어를 포함하세요.
        JSON 배열(list) 형태로만 출력하세요.
        """
        try:
            resp = openai.ChatCompletion.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            content = resp.choices[0].message["content"].strip()
            data = json.loads(content)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
            return []
        except Exception as e:
            print(f"⚠️ GPT 변환 실패: {e}")
            return []

    # -------------------------------------
    # 통합 정규화
    # -------------------------------------
    def normalize(self, query: str):
        """CSV + AI 결과 병합"""
        csv_terms = self.map_with_csv(query)
        ai_terms = self.map_with_ai(query)
        bundle = [query] + csv_terms + ai_terms
        bundle = [t for t in bundle if t]
        bundle = sorted(list(set(bundle)), key=lambda x: len(x))
        return bundle[:12]  # 최대 12개까지만
