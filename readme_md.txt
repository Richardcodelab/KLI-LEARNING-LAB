# 🔎 러닝랩 학술 검색 시스템

KCI(한국학술정보원)와 RISS(학술연구정보서비스)를 통합 검색하는 AI 기반 학술 논문 검색 시스템

## ✨ 주요 기능

### 1. 자연어 검색
- 일상적인 문장으로 검색 가능
- 예: "청년에게 신용 제약이 미치는 영향"

### 2. AI 검색어 확장
- GPT를 활용한 자동 키워드 생성
- CSV 기반 동의어 매핑
- 불용어 자동 제거

### 3. 멀티소스 검색
- KCI: 한국 학술 논문
- RISS: 국내외 학위/학술 논문
- 다중 전략 검색으로 최대 결과 확보

### 4. 데이터 처리
- 자동 중복 제거 (DOI 기반)
- 표준화된 컬럼 구조
- 초록/키워드 자동 보강

### 5. 시각화 및 분석
- 연도별 논문 분포
- 소스별/발행처별 통계
- 검색 품질 분석

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 저장소 클론 (또는 파일 다운로드)
git clone https://github.com/your-repo/learning-lab-search.git
cd learning-lab-search

# 가상환경 생성 (선택사항)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt
```

### 2. API 키 설정

`.env.example`을 `.env`로 복사하고 API 키 입력:

```bash
cp .env.example .env
```

`.env` 파일 편집:
```
OPENAI_API_KEY=sk-...
KCI_API_KEY=your_key
RISS_API_KEY=your_key
```

### 3. 실행

```bash
# Streamlit 웹 앱 실행
streamlit run app.py

# 또는 개별 스크립트 실행
python KCI_collector.py
python RISS_collector.py
```

## 📂 프로젝트 구조

```
learning-lab-search/
├── app.py                      # Streamlit 웹 인터페이스
├── query_normalizer.py         # 검색어 정규화 모듈
├── KCI_collector.py            # KCI API 수집기
├── RISS_collector.py           # RISS API 수집기
├── keyword_mapping.csv         # 검색어 매핑표
├── requirements.txt            # 필수 패키지
├── .env.example                # 환경 변수 예시
└── README.md                   # 이 파일
```

## 🎯 사용 방법

### 웹 인터페이스 (권장)

1. `streamlit run app.py` 실행
2. 브라우저에서 http://localhost:8501 접속
3. 검색어 입력 후 "검색 실행" 클릭
4. 결과 확인 및 다운로드

### 프로그래밍 방식

```python
from query_normalizer import QueryNormalizer
from KCI_collector import OptimizedKCIAnalyzer
from RISS_collector import ImprovedRISSAnalyzer

# 1. 검색어 정규화
normalizer = QueryNormalizer(use_ai=True)
terms = normalizer.normalize("청년 고용 문제")
print(terms)  # ['청년', '고용', '취업', '일자리', ...]

# 2. KCI 검색
kci = OptimizedKCIAnalyzer(api_key="your_key")
result = kci.search_articles(
    title="청년 고용",
    date_from="202001",
    date_to="202512"
)
df_kci = kci.extract_article_info_optimized(result)

# 3. RISS 검색
riss = ImprovedRISSAnalyzer(api_key="your_key")
results_riss = riss.search_with_multiple_strategies(
    "청년 고용",
    start_year=2020,
    end_year=2025
)
df_riss = pd.DataFrame(results_riss)

# 4. 병합 및 저장
# ... (상세 코드는 app.py 참고)
```

## 📋 CSV 매핑표 형식

`keyword_mapping.csv`:

```csv
user_pattern,canonical_term,category,synonyms,weight
청년,청년,인구,젊은층|20대|30대,1.0
고용,고용,경제,취업|일자리|채용,1.0
```

**컬럼 설명:**
- `user_pattern`: 사용자 입력 패턴
- `canonical_term`: 표준 검색어
- `category`: 카테고리
- `synonyms`: 동의어 (| 구분)
- `weight`: 가중치 (0.0~1.0)

## 🔧 고급 설정

### 검색 전략 커스터마이징

```python
# KCI: 상세 정보 자동 조회 비활성화
df = kci.extract_article_info_optimized(
    result, 
    fetch_details=False
)

# RISS: 특정 문서 타입만 검색
results = riss.search_with_multiple_strategies(
    "고용",
    doc_type="A",  # A: 국내학술, T: 학위논문, F: 해외학술
    max_results=500
)
```

### 캐시 관리

```python
# AI 캐시 초기화
normalizer.clear_cache()

# 통계 확인
stats = normalizer.get_statistics()
print(stats)
```

## 📊 출력 데이터 구조

### 통합 DataFrame 컬럼

| 컬럼명 | 설명 | 예시 |
|--------|------|------|
| title | 논문 제목 | "청년 고용과 경제 성장" |
| authors | 저자 | "홍길동; 김철수" |
| venue | 발행처/학술지 | "한국경제학회" |
| pub_year | 발행연도 | "2023" |
| url | 논문 URL | "https://..." |
| doi | DOI | "10.1234/..." |
| abstract | 초록 | "본 연구는..." |
| keywords | 키워드 | "청년; 고용; 일자리" |
| source | 데이터 소스 | "KCI" / "RISS" |
| query_term | 검색 키워드 | "청년 고용" |

## 🐛 문제 해결

### API 오류

```
❌ HTTP 오류: 403
```
→ API 키 확인 또는 재발급

### 한글 깨짐

```python
# CSV 읽기 시 인코딩 지정
df = pd.read_csv("file.csv", encoding="utf-8-sig")
```

### 검색 결과 없음

1. 검색어를 더 일반적으로 변경
2. 연도 범위 확대
3. "상세 로그" 활성화하여 오류 확인

### OpenAI API 오류

```
❌ AI 검색어 생성 실패
```
→ `.env` 파일의 `OPENAI_API_KEY` 확인
→ `use_ai=False`로 GPT 비활성화 가능

## 💡 팁

### 효율적인 검색

1. **구체적 키워드**: "논문" ❌ → "청년 고용 불안정" ✅
2. **CSV 매핑 활용**: 자주 쓰는 검색어 등록
3. **연도 범위 제한**: 최근 5년으로 좁히기
4. **초록 필터**: 초록 있는 논문만 선택

### 성능 최적화

```python
# KCI: 병렬 처리 워커 수 조정
details = kci.get_article_detail_batch(ids, max_workers=10)

# RISS: 타임아웃 조정
riss.session.timeout = 30
```

## 📈 업데이트 내역

### v2.0.0 (2025-01-XX)
- ✨ Streamlit UI 리뉴얼
- 🚀 병렬 처리로 성능 3배 향상
- 🛡️ 에러 처리 강화
- 📊 실시간 통계 및 시각화
- 🔍 다중 전략 검색 추가
- 💾 필터링 기능 강화

### v1.0.0 (2024-XX-XX)
- 🎉 초기 릴리스
- KCI/RISS 기본 검색 기능
- CSV 기반 매핑

## 🤝 기여하기

이슈 제보 및 PR 환영합니다!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이선스

MIT License - 자유롭게 사용 가능

## 📞 문의

- 프로젝트 관리자: 러닝랩 팀
- 이메일: contact@learninglab.kr
- 이슈: [GitHub Issues](https://github.com/your-repo/issues)

---

**Made with ❤️ by 러닝랩 팀**
