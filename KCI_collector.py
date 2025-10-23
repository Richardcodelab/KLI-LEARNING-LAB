import requests
import xml.etree.ElementTree as ET
import pandas as pd
import json
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
import re
from urllib.parse import quote
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_korean_font():
    """한글 폰트 설정"""
    import matplotlib.font_manager as fm
    
    system = platform.system()
    
    if system == 'Windows':
        font_names = ['Malgun Gothic', 'Microsoft YaHei', 'NanumGothic', 'SimHei', 'Arial Unicode MS']
    elif system == 'Darwin':  # macOS
        font_names = ['AppleGothic', 'Apple SD Gothic Neo', 'Helvetica', 'Arial Unicode MS']
    else:  # Linux
        font_names = ['NanumGothic', 'DejaVu Sans', 'Liberation Sans']
    
    available_fonts = [f.name for f in fm.fontManager.ttflist]
    
    selected_font = None
    for font_name in font_names:
        if font_name in available_fonts:
            selected_font = font_name
            plt.rcParams['font.family'] = font_name
            break
    
    if selected_font is None:
        plt.rcParams['font.family'] = 'DejaVu Sans'
        selected_font = 'DejaVu Sans'
        logger.warning("⚠️ 한글 폰트를 찾을 수 없어 기본 폰트를 사용합니다.")
    
    plt.rcParams['axes.unicode_minus'] = False
    
    try:
        fm._rebuild()
    except:
        pass
    
    logger.info(f"✅ 설정된 폰트: {selected_font}")
    return selected_font


setup_korean_font()


class OptimizedKCIAnalyzer:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"
        self.headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # 캐시 저장소
        self.detail_cache = {}
        
    def search_articles(self, title=None, author=None, journal=None, 
                       date_from=None, date_to=None, page=1, display_count=10):
        """논문 기본 정보 검색"""
        params = {
            'apiCode': 'articleSearch',
            'key': self.api_key,
            'page': page,
            'displayCount': min(display_count, 100)
        }
        
        if title:
            params['title'] = title
        if author:
            params['author'] = author
        if journal:
            params['journal'] = journal
        if date_from:
            params['dateFrom'] = date_from
        if date_to:
            params['dateTo'] = date_to
            
        logger.info(f"🔍 KCI API 호출 (페이지 {page}, {display_count}건)...")
        
        try:
            response = self.session.get(self.base_url, params=params, timeout=15)
            
            if response.status_code == 200:
                root = ET.fromstring(response.text)
                result = self._xml_to_dict(root)
                logger.info(f"✅ API 호출 성공")
                return result
            else:
                logger.error(f"❌ HTTP 오류: {response.status_code}")
                return None
            
        except requests.Timeout:
            logger.error("❌ API 요청 타임아웃")
            return None
        except Exception as e:
            logger.error(f"❌ API 요청 오류: {e}")
            return None
    
    def get_article_detail_batch(self, article_ids, max_workers=5):
        """배치로 상세 정보 조회 - 병렬 처리"""
        details = {}
        
        def fetch_detail(article_id):
            if article_id in self.detail_cache:
                return article_id, self.detail_cache[article_id]
            
            params = {
                'apiCode': 'articleDetail',
                'key': self.api_key,
                'id': article_id
            }
            
            try:
                response = self.session.get(self.base_url, params=params, timeout=10)
                if response.status_code == 200:
                    root = ET.fromstring(response.text)
                    result = self._xml_to_dict(root)
                    self.detail_cache[article_id] = result
                    return article_id, result
                else:
                    return article_id, None
            except Exception as e:
                logger.warning(f"⚠️ 상세 정보 조회 실패 ({article_id}): {e}")
                return article_id, None
        
        logger.info(f"🔍 {len(article_ids)}개 논문 상세 정보 병렬 조회...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_id = {executor.submit(fetch_detail, aid): aid for aid in article_ids}
            
            for future in as_completed(future_to_id):
                article_id, result = future.result()
                if result:
                    details[article_id] = result
                time.sleep(0.1)  # API 호출 간격 조절
        
        logger.info(f"✅ {len(details)}개 상세 정보 조회 완료")
        return details
    
    def _xml_to_dict(self, element):
        """최적화된 XML to Dict 변환"""
        result = {}
        
        if element.text and element.text.strip():
            result['text'] = element.text.strip()
        
        if element.attrib:
            result.update(element.attrib)
        
        for child in element:
            child_data = self._xml_to_dict(child)
            if child.tag in result:
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_data)
            else:
                result[child.tag] = child_data
        
        return result
    
    def _extract_text_fast(self, data):
        """빠른 텍스트 추출"""
        if data is None:
            return ''
        
        if isinstance(data, str):
            return data.strip()
        
        if isinstance(data, dict):
            if 'text' in data:
                return str(data['text']).strip()
            
            for key in ['#text', 'content', 'value']:
                if key in data:
                    return str(data[key]).strip()
            
            if len(data) == 1:
                key, value = next(iter(data.items()))
                if key not in ['lang', 'type', 'id']:
                    return self._extract_text_fast(value)
            
            return ''
        
        if isinstance(data, list) and data:
            return self._extract_text_fast(data[0])
        
        return str(data).strip() if data else ''
    
    def _extract_keywords_optimized(self, article_info, detail_info=None):
        """최적화된 키워드 추출"""
        keyword_sources = [
            (article_info, ['keyword-group', 'keyword']),
            (article_info, ['kwd-group', 'kwd']),
            (article_info, ['keywords']),
            (article_info, ['keyword']),
        ]
        
        # 상세 정보가 있으면 추가
        if detail_info:
            detail_article_info = detail_info.get('outputData', {}).get('record', {}).get('articleInfo', {})
            keyword_sources.extend([
                (detail_article_info, ['keyword-group', 'keyword']),
                (detail_article_info, ['kwd-group', 'kwd']),
            ])
        
        for source_data, path in keyword_sources:
            keywords = self._extract_from_path(source_data, path)
            if keywords:
                return '; '.join(keywords)
        
        return ''
    
    def _extract_from_path(self, data, path):
        """경로를 따라 데이터 추출"""
        current = data
        
        for key in path[:-1]:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return []
        
        if not isinstance(current, dict) or path[-1] not in current:
            return []
        
        keyword_data = current[path[-1]]
        keywords = []
        
        if isinstance(keyword_data, list):
            for item in keyword_data:
                text = self._extract_text_fast(item)
                if text:
                    keywords.append(text)
        else:
            text = self._extract_text_fast(keyword_data)
            if text:
                keywords.append(text)
        
        return keywords

    def _extract_abstract_optimized(self, article_info):
        """상세 응답(articleInfo)에서 초록 텍스트를 최대한 탄력적으로 추출"""
        if not isinstance(article_info, dict):
            return ''

        candidates = [
            ['abstract'],
            ['abstract-group', 'abstract'],
            ['abstract', 'p'],
            ['abstract', 'text'],
            ['abstract-group', 'abstract', 'p'],
            ['abstract-group', 'abstract', 'text'],
        ]

        for path in candidates:
            cur = article_info
            ok = True
            for key in path:
                if isinstance(cur, dict) and key in cur:
                    cur = cur[key]
                else:
                    ok = False
                    break
            if ok:
                txt = self._extract_text_fast(cur)
                if txt:
                    return txt
        return ''
    
    def extract_article_info_optimized(self, api_response, fetch_details=True, detail_batch_size=10):
        """최적화된 논문 정보 추출"""
        if not api_response:
            return pd.DataFrame()
        
        start_time = time.time()
        articles = []
        
        try:
            output_data = api_response.get('outputData', {})
            records = output_data.get('record', [])
            
            if isinstance(records, dict):
                records = [records]
            
            logger.info(f"📊 {len(records)}개 논문 데이터 처리 중...")
            
            # 1단계: 기본 정보 빠르게 추출
            article_ids_need_detail = []
            
            for i, record in enumerate(records):
                article = self._extract_basic_info(record)
                articles.append(article)
                
                # 키워드나 초록이 없으면 상세 조회
                needs_detail = (
                    (not article.get('keywords')) or
                    (not article.get('abstract'))
                )
                if needs_detail and article.get('article_id') and fetch_details:
                    article_ids_need_detail.append((i, article['article_id']))
            
            logger.info(f"⚡ 1단계 완료: {len(articles)}개 기본 정보 추출 ({time.time() - start_time:.1f}초)")
            
            # 2단계: 상세 조회로 키워드/초록 보강
            if article_ids_need_detail:
                batch_start = time.time()
                ids_only = [aid for _, aid in article_ids_need_detail]
                details = self.get_article_detail_batch(ids_only, max_workers=5)
                
                for i, article_id in article_ids_need_detail:
                    if article_id in details:
                        detail_info = details[article_id]
                        # 키워드 보강
                        enhanced_keywords = self._extract_keywords_optimized(
                            records[i].get('articleInfo', {}), detail_info
                        )
                        if enhanced_keywords and not articles[i].get('keywords'):
                            articles[i]['keywords'] = enhanced_keywords

                        # 초록 보강
                        if not articles[i].get('abstract'):
                            detail_article_info = detail_info.get('outputData', {}).get('record', {}).get('articleInfo', {})
                            enhanced_abs = self._extract_abstract_optimized(detail_article_info)
                            if enhanced_abs:
                                articles[i]['abstract'] = enhanced_abs
                
                logger.info(f"⚡ 2단계 완료: {len(details)}개 상세 정보 보강 ({time.time() - batch_start:.1f}초)")
            
            logger.info(f"🚀 전체 처리 완료: {time.time() - start_time:.1f}초")
            
        except Exception as e:
            logger.error(f"❌ 데이터 추출 중 오류: {e}")
            import traceback
            traceback.print_exc()
        
        return pd.DataFrame(articles)
    
    def _extract_basic_info(self, record):
        """기본 정보 빠른 추출"""
        article = {}
        
        # 저널 정보
        journal_info = record.get('journalInfo', {})
        article['journal_name'] = self._extract_text_fast(journal_info.get('journal-name', {}))
        article['publisher_name'] = self._extract_text_fast(journal_info.get('publisher-name', {}))
        article['pub_year'] = self._extract_text_fast(journal_info.get('pub-year', {}))
        article['pub_mon'] = self._extract_text_fast(journal_info.get('pub-mon', {}))
        article['volume'] = self._extract_text_fast(journal_info.get('volume', {}))
        article['issue'] = self._extract_text_fast(journal_info.get('issue', {}))
        
        # 논문 정보
        article_info = record.get('articleInfo', {})
        article['article_id'] = article_info.get('article-id', '')
        article['categories'] = self._extract_text_fast(article_info.get('article-categories', {}))
        article['regularity'] = self._extract_text_fast(article_info.get('article-regularity', {}))
        
        # 제목
        title_group = article_info.get('title-group', {})
        article_title = title_group.get('article-title', {})
        
        if isinstance(article_title, list):
            title_text = self._extract_text_fast(article_title[0])
        else:
            title_text = self._extract_text_fast(article_title)
        
        article['title'] = title_text or '제목 없음'
        
        # 저자
        author_group = article_info.get('author-group', {})
        authors = author_group.get('author', [])
        if isinstance(authors, dict):
            authors = [authors]
        
        author_names = []
        for author in authors[:5]:  # 최대 5명만 처리
            author_text = self._extract_text_fast(author)
            if author_text:
                author_names.append(author_text)
        
        article['authors'] = '; '.join(author_names)
        
        # 초록
        abstract_text = self._extract_text_fast(article_info.get('abstract', {}))
        if not abstract_text:
            abstract_group = article_info.get('abstract-group', {})
            if abstract_group:
                abstract = abstract_group.get('abstract', {})
                abstract_text = self._extract_text_fast(abstract)
        
        article['abstract'] = abstract_text
        
        # 키워드
        article['keywords'] = self._extract_keywords_optimized(article_info)
        
        # 기타 정보
        article['fpage'] = self._extract_text_fast(article_info.get('fpage', {}))
        article['lpage'] = self._extract_text_fast(article_info.get('lpage', {}))
        article['doi'] = self._extract_text_fast(article_info.get('doi', {}))
        article['uci'] = self._extract_text_fast(article_info.get('uci', {}))
        
        citation_count = article_info.get('citation-count', {})
        article['citation_count'] = self._extract_text_fast(citation_count) or '0'
        article['kci_citations'] = citation_count.get('kci', '0')
        article['wos_citations'] = citation_count.get('wos', '0')
        
        article['url'] = self._extract_text_fast(article_info.get('url', {}))
        article['verified'] = self._extract_text_fast(article_info.get('verified', {}))
        article['orte_open_yn'] = self._extract_text_fast(article_info.get('orte-open-yn', {}))
        
        return article
    
    def analyze_by_year(self, df):
        """연도별 논문 발행 분석"""
        if df.empty or 'pub_year' not in df.columns:
            return pd.Series()
        
        df_copy = df.copy()
        df_copy['pub_year'] = pd.to_numeric(df_copy['pub_year'], errors='coerce')
        df_filtered = df_copy[df_copy['pub_year'].notna() & 
                             (df_copy['pub_year'] >= 1900) & 
                             (df_copy['pub_year'] <= 2025)]
        
        return df_filtered['pub_year'].value_counts().sort_index()
    
    def analyze_journals(self, df, top_n=10):
        """학술지별 논문 수 분석"""
        if df.empty or 'journal_name' not in df.columns:
            return pd.Series()
        
        return df[df['journal_name'] != '']['journal_name'].value_counts().head(top_n)
    
    def analyze_categories(self, df, top_n=10):
        """연구분야별 논문 수 분석"""
        if df.empty or 'categories' not in df.columns:
            return pd.Series()
        
        return df[df['categories'] != '']['categories'].value_counts().head(top_n)
    
    def analyze_keywords(self, df, top_n=15):
        """키워드 빈도 분석"""
        if df.empty or 'keywords' not in df.columns:
            return pd.Series()
        
        all_keywords = []
        for keywords_str in df['keywords'].dropna():
            if keywords_str and str(keywords_str).strip():
                keywords = re.split('[;,/]', str(keywords_str))
                for kw in keywords:
                    kw = kw.strip()
                    if kw and len(kw) > 1:
                        all_keywords.append(kw)
        
        if all_keywords:
            keyword_counts = pd.Series(all_keywords).value_counts().head(top_n)
            return keyword_counts
        else:
            return pd.Series()
    
    def export_to_excel(self, df, filename, search_term):
        """Excel 파일로 내보내기"""
        try:
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                # 논문 데이터
                df.to_excel(writer, sheet_name='논문_데이터', index=False)
                
                # 연도별 분석
                year_analysis = self.analyze_by_year(df)
                if not year_analysis.empty:
                    year_df = pd.DataFrame({'연도': year_analysis.index, '논문수': year_analysis.values})
                    year_df.to_excel(writer, sheet_name='연도별_분석', index=False)
                
                # 학술지별 분석
                journal_analysis = self.analyze_journals(df)
                if not journal_analysis.empty:
                    journal_df = pd.DataFrame({'학술지': journal_analysis.index, '논문수': journal_analysis.values})
                    journal_df.to_excel(writer, sheet_name='학술지별_분석', index=False)
                
                # 키워드 분석
                keyword_analysis = self.analyze_keywords(df)
                if not keyword_analysis.empty:
                    keyword_df = pd.DataFrame({'키워드': keyword_analysis.index, '빈도': keyword_analysis.values})
                    keyword_df.to_excel(writer, sheet_name='키워드_분석', index=False)
            
            logger.info(f"✅ 데이터가 {filename}에 저장되었습니다.")
            
        except Exception as e:
            logger.error(f"❌ 파일 저장 중 오류: {e}")


if __name__ == "__main__":
    # 테스트 코드
    api_key = "30354185"
    analyzer = OptimizedKCIAnalyzer(api_key)
    
    result = analyzer.search_articles(
        title="고용",
        date_from="201501",
        date_to="202512",
        page=1,
        display_count=50
    )
    
    if result:
        df = analyzer.extract_article_info_optimized(result, fetch_details=True)
        print(f"\n✅ 추출된 논문 수: {len(df)}건")
        print(df.head())