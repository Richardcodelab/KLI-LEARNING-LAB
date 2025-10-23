import requests
import xml.etree.ElementTree as ET
import pandas as pd
import json
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
import re
from urllib.parse import quote, urlencode
import platform
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
    
    # 사용 가능한 폰트 찾기
    available_fonts = [f.name for f in fm.fontManager.ttflist]
    
    selected_font = None
    for font_name in font_names:
        if font_name in available_fonts:
            selected_font = font_name
            plt.rcParams['font.family'] = font_name
            break
    
    if selected_font is None:
        # 기본 폰트로 설정
        plt.rcParams['font.family'] = 'DejaVu Sans'
        selected_font = 'DejaVu Sans'
        logger.warning("⚠️ 한글 폰트를 찾을 수 없어 기본 폰트를 사용합니다.")
    
    plt.rcParams['axes.unicode_minus'] = False
    
    # 폰트 캐시 새로고침
    try:
        fm._rebuild()
    except:
        pass
    
    logger.info(f"✅ 설정된 폰트: {selected_font}")
    return selected_font


setup_korean_font()


class ImprovedRISSAnalyzer:
    def __init__(self, api_key=None):
        """개선된 RISS API 분석 클래스"""
        self.api_key = api_key or '70aaa00wqm60acd00aaa00ab01za061a'
        self.base_url = "http://www.riss.kr/openApi"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/xml,text/xml,*/*',
            'Accept-Language': 'ko-KR,ko;q=0.8',
            'Connection': 'keep-alive'
        }
        self.all_results = []  # 모든 검색 결과 저장
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def _extract_text(self, data):
        """데이터에서 텍스트 추출"""
        try:
            if isinstance(data, dict):
                if 'text' in data:
                    return str(data['text']).strip()
                elif '#text' in data:
                    return str(data['#text']).strip()
                elif data:
                    return str(list(data.values())[0]).strip()
                else:
                    return ''
            elif isinstance(data, str):
                return data.strip()
            elif isinstance(data, list) and data:
                return self._extract_text(data[0])
            elif data is None:
                return ''
            else:
                return str(data).strip()
        except Exception as e:
            logger.warning(f"텍스트 추출 오류: {e}")
            return ''
    
    def search_with_multiple_strategies(self, search_term, doc_type='T', 
                                       start_year=2015, end_year=2025, max_results=200):
        """
        다중 검색 전략을 사용한 논문 검색
        1. 제목 전용 검색 (정확도 높음)
        2. 키워드 전체 검색 (범위 넓음)  
        3. 연도별 분할 검색 (개수 제한 우회)
        """
        logger.info(f"=== 개선된 RISS 검색 시작 ===")
        logger.info(f"검색어: {search_term}")
        logger.info(f"기간: {start_year}-{end_year}")
        logger.info(f"목표 개수: {max_results}")
        
        all_results = []
        search_stats = {
            'title_search': 0,
            'keyword_search': 0,
            'yearly_search': 0,
            'errors': []
        }
        
        # 전략 1: 제목 전용 검색 (높은 정확도)
        logger.info("\n🎯 전략 1: 제목 전용 검색")
        title_results = self._search_by_title(search_term, doc_type, start_year, end_year, 100)
        if title_results:
            all_results.extend(title_results)
            search_stats['title_search'] = len(title_results)
            logger.info(f"제목 검색 결과: {len(title_results)}건")
        
        # 전략 2: 키워드 전체 검색 (넓은 범위)
        if len(all_results) < max_results:
            logger.info("\n🔍 전략 2: 키워드 전체 검색")
            keyword_results = self._search_by_keyword(
                search_term, doc_type, start_year, end_year, 
                max_results - len(all_results)
            )
            if keyword_results:
                # 중복 제거 (URL 기준)
                existing_urls = {r.get('url', '') for r in all_results}
                new_results = [r for r in keyword_results if r.get('url', '') not in existing_urls]
                all_results.extend(new_results)
                search_stats['keyword_search'] = len(new_results)
                logger.info(f"키워드 검색 결과: {len(keyword_results)}건 (중복 제거 후: {len(new_results)}건)")
        
        # 전략 3: 연도별 분할 검색 (API 제한 우회)
        if len(all_results) < max_results:
            logger.info("\n📅 전략 3: 연도별 분할 검색")
            yearly_results = self._search_by_years(
                search_term, doc_type, start_year, end_year, 
                max_results - len(all_results)
            )
            if yearly_results:
                existing_urls = {r.get('url', '') for r in all_results}
                new_results = [r for r in yearly_results if r.get('url', '') not in existing_urls]
                all_results.extend(new_results)
                search_stats['yearly_search'] = len(new_results)
                logger.info(f"연도별 검색 결과: {len(yearly_results)}건 (중복 제거 후: {len(new_results)}건)")
        
        logger.info(f"\n✅ 총 검색 결과: {len(all_results)}건")
        logger.info(f"   - 제목 검색: {search_stats['title_search']}건")
        logger.info(f"   - 키워드 검색: {search_stats['keyword_search']}건")
        logger.info(f"   - 연도별 검색: {search_stats['yearly_search']}건")
        
        self.all_results = all_results
        return all_results
    
    def _search_by_title(self, search_term, doc_type, start_year, end_year, count):
        """제목 전용 검색"""
        params = {
            'key': self.api_key,
            'version': '1.0',
            'type': doc_type,
            'title': search_term,  # 제목에서만 검색
            'spubdate': start_year,
            'epubdate': end_year,
            'sort': 'Y',
            'asc': 'D',
            'rsnum': 1,
            'rowcount': min(count, 100)
        }
        
        return self._execute_search(params, "제목 검색")
    
    def _search_by_keyword(self, search_term, doc_type, start_year, end_year, count):
        """키워드 전체 검색"""
        params = {
            'key': self.api_key,
            'version': '1.0',
            'type': doc_type,
            'keyword': search_term,  # 전체에서 검색
            'spubdate': start_year,
            'epubdate': end_year,
            'sort': 'Y',
            'asc': 'D',
            'rsnum': 1,
            'rowcount': min(count, 100)
        }
        
        return self._execute_search(params, "키워드 검색")
    
    def _search_by_years(self, search_term, doc_type, start_year, end_year, remaining_count):
        """연도별 분할 검색 (API 제한 우회)"""
        results = []
        per_year = max(10, remaining_count // (end_year - start_year + 1))
        
        for year in range(start_year, end_year + 1):
            if len(results) >= remaining_count:
                break
                
            params = {
                'key': self.api_key,
                'version': '1.0', 
                'type': doc_type,
                'keyword': search_term,
                'spubdate': year,
                'epubdate': year,
                'sort': 'Y',
                'asc': 'D',
                'rsnum': 1,
                'rowcount': min(per_year, 100)
            }
            
            year_results = self._execute_search(params, f"{year}년 검색", verbose=False)
            if year_results:
                results.extend(year_results)
                logger.info(f"  {year}년: {len(year_results)}건")
                time.sleep(0.5)  # API 호출 간격
        
        return results
    
    def _execute_search(self, params, search_type, verbose=True):
        """실제 API 호출 실행"""
        try:
            if verbose:
                logger.info(f"  {search_type} 실행중...")
            
            response = self.session.get(
                self.base_url, 
                params=params, 
                timeout=15
            )
            
            if response.status_code == 200:
                # XML 파싱
                root = ET.fromstring(response.text)
                result = self._xml_to_dict(root)
                
                # 결과 추출
                articles = self._extract_articles_from_response(result)
                return articles
            else:
                logger.error(f"    ❌ HTTP 오류: {response.status_code}")
                return []
                
        except requests.Timeout:
            logger.error(f"    ❌ {search_type} 타임아웃")
            return []
        except ET.ParseError as e:
            logger.error(f"    ❌ XML 파싱 오류: {e}")
            return []
        except Exception as e:
            logger.error(f"    ❌ {search_type} 오류: {e}")
            return []
    
    def _xml_to_dict(self, element):
        """XML을 딕셔너리로 변환"""
        result = {}
        
        if element.text and element.text.strip():
            result['text'] = element.text.strip()
        
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
    
    def _extract_articles_from_response(self, api_response):
        """API 응답에서 논문 정보 추출"""
        if not api_response:
            return []
        
        articles = []
        
        try:
            if 'head' in api_response and 'metadata' in api_response:
                head = api_response['head']
                total_count = self._extract_text(head.get('totalcount', ''))
                error = self._extract_text(head.get('Error', ''))
                
                if error != '0':
                    error_msg = self._extract_text(head.get('ErrorMessage', '알 수 없는 오류'))
                    logger.warning(f"API 오류: {error_msg}")
                    return []
                
                metadata = api_response['metadata']
                if isinstance(metadata, dict):
                    metadata = [metadata]
                
                for record in metadata:
                    try:
                        article = {
                            'title': self._extract_text(record.get('riss.title', '')),
                            'author': self._extract_text(record.get('riss.author', '')),
                            'publisher': self._extract_text(record.get('riss.publisher', '')),
                            'pub_year': self._extract_text(record.get('riss.pubdate', '')),
                            'doc_type': self._extract_text(record.get('riss.type', '')),
                            'material_type': self._extract_text(record.get('riss.mtype', '')),
                            'url': self._extract_text(record.get('url', '')),
                            'has_abstract': self._extract_text(record.get('riss.abstract', '')),
                            'has_toc': self._extract_text(record.get('riss.toc', '')),
                            'has_image': self._extract_text(record.get('riss.image', ''))
                        }
                        
                        # 자료 유형 변환
                        doc_type_map = {
                            'T': '학위논문',
                            'A': '국내학술논문', 
                            'F': '해외학술논문'
                        }
                        article['doc_type_name'] = doc_type_map.get(
                            article['doc_type'], 
                            article['doc_type']
                        )
                        
                        # 빈 값 처리
                        for key in article:
                            if article[key] is None:
                                article[key] = ''
                        
                        # 제목이 없는 논문은 제외
                        if article['title']:
                            articles.append(article)
                        
                    except Exception as e:
                        logger.warning(f"논문 정보 추출 실패: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"데이터 추출 오류: {e}")
            
        return articles
    
    def analyze_search_quality(self, search_term, results):
        """검색 품질 분석"""
        if not results:
            return {}
        
        # 검색어에서 핵심 키워드 추출
        core_keywords = [search_term.lower()]
        
        # CSV에서 동의어 가져오기 (간단 버전)
        keyword_variants = {
            '고용': ['고용', '취업', '일자리', '채용', '직업', '근로', '근무', '직장', '노동', 
                   'employment', 'job', 'work', 'career', 'occupation', 'labor'],
            '교육': ['교육', '학습', '교수', '학교', '대학', '연수', '훈련', '강의', '수업',
                   'education', 'learning', 'teaching', 'school', 'university'],
            '의료': ['의료', '병원', '치료', '진료', '간호', '의사', '환자', '건강', '질병',
                   'medical', 'hospital', 'treatment', 'healthcare', 'doctor'],
        }
        
        # 검색어에 해당하는 변형어 찾기
        related_keywords = []
        for key, variants in keyword_variants.items():
            if key in search_term.lower():
                related_keywords.extend([v.lower() for v in variants])
        
        if not related_keywords:
            related_keywords = core_keywords
        
        related_count = 0
        year_distribution = {}
        
        for paper in results:
            title_lower = str(paper.get('title', '')).lower()
            author_lower = str(paper.get('author', '')).lower()
            
            # 관련성 체크
            if any(keyword in title_lower or keyword in author_lower 
                   for keyword in related_keywords):
                related_count += 1
            
            # 연도 분포
            year = paper.get('pub_year', '')
            if year:
                # 연도 추출 (YYYY 형식)
                year_match = re.search(r'(\d{4})', str(year))
                if year_match:
                    year = year_match.group(1)
                    year_distribution[year] = year_distribution.get(year, 0) + 1
        
        analysis = {
            'total_papers': len(results),
            'related_papers': related_count,
            'relevance_rate': (related_count / len(results)) * 100 if results else 0,
            'year_distribution': year_distribution,
            'year_range': (
                f"{min(year_distribution.keys()) if year_distribution else 'N/A'} - "
                f"{max(year_distribution.keys()) if year_distribution else 'N/A'}"
            )
        }
        
        return analysis
    
    def create_dataframe(self, results):
        """결과를 DataFrame으로 변환"""
        return pd.DataFrame(results)
    
    def analyze_by_year(self, df):
        """연도별 논문 발행 분석"""
        if df.empty or 'pub_year' not in df.columns:
            return pd.Series()
        
        df_copy = df.copy()
        df_copy['pub_year'] = df_copy['pub_year'].astype(str)
        df_copy['pub_year'] = df_copy['pub_year'].str.extract(r'(\d{4})').iloc[:, 0]
        df_copy['pub_year'] = pd.to_numeric(df_copy['pub_year'], errors='coerce')
        
        df_filtered = df_copy[
            df_copy['pub_year'].notna() & 
            (df_copy['pub_year'] >= 1900) & 
            (df_copy['pub_year'] <= 2025)
        ]
        
        return df_filtered['pub_year'].value_counts().sort_index()
    
    def analyze_publishers(self, df, top_n=10):
        """출판사/기관별 논문 수 분석"""
        if df.empty or 'publisher' not in df.columns:
            return pd.Series()
        
        return df[df['publisher'] != '']['publisher'].value_counts().head(top_n)
    
    def analyze_material_types(self, df, top_n=10):
        """세부 자료 유형별 분석 (국내박사, 국내석사 등)"""
        if df.empty or 'material_type' not in df.columns:
            return pd.Series()
        
        return df[df['material_type'] != '']['material_type'].value_counts().head(top_n)
    
    def analyze_doc_types(self, df, top_n=10):
        """자료 유형별 분석"""
        if df.empty or 'doc_type_name' not in df.columns:
            return pd.Series()
        
        return df[df['doc_type_name'] != '']['doc_type_name'].value_counts().head(top_n)
    
    def export_results(self, results, filename, search_term):
        """결과를 Excel로 내보내기"""
        if not results:
            logger.warning("내보낼 데이터가 없습니다.")
            return
        
        df = pd.DataFrame(results)
        analysis = self.analyze_search_quality(search_term, results)
        
        try:
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                # 논문 데이터
                df.to_excel(writer, sheet_name='논문_데이터', index=False)
                
                # 검색 품질 분석
                quality_df = pd.DataFrame([analysis])
                quality_df.to_excel(writer, sheet_name='검색_품질_분석', index=False)
                
                # 연도별 분포
                if analysis['year_distribution']:
                    year_df = pd.DataFrame(
                        list(analysis['year_distribution'].items()), 
                        columns=['연도', '논문수']
                    )
                    year_df = year_df.sort_values('연도')
                    year_df.to_excel(writer, sheet_name='연도별_분포', index=False)
                
                # 출판기관별 분포
                publisher_analysis = self.analyze_publishers(df)
                if not publisher_analysis.empty:
                    pub_df = pd.DataFrame({
                        '출판기관': publisher_analysis.index, 
                        '논문수': publisher_analysis.values
                    })
                    pub_df.to_excel(writer, sheet_name='출판기관별_분석', index=False)
            
            logger.info(f"✅ 데이터가 {filename}에 저장되었습니다.")
            
        except Exception as e:
            logger.error(f"❌ 파일 저장 오류: {e}")


def main():
    """개선된 메인 실행 함수"""
    # 검색 설정
    search_term = "고용"
    doc_type = "T"  # T: 학위논문
    start_year = 2015
    end_year = 2025
    max_results = 200
    
    logger.info("=== 개선된 RISS 논문 검색 도구 ===")
    logger.info(f"검색어: {search_term}")
    logger.info(f"자료유형: {'학위논문' if doc_type == 'T' else '학술논문'}")
    logger.info(f"검색기간: {start_year}-{end_year}")
    logger.info(f"목표건수: {max_results}\n")
    
    # 분석기 초기화
    analyzer = ImprovedRISSAnalyzer()
    
    # 다중 전략 검색 실행
    start_time = time.time()
    results = analyzer.search_with_multiple_strategies(
        search_term, doc_type, start_year, end_year, max_results
    )
    search_time = time.time() - start_time
    
    if results:
        # 검색 품질 분석
        analysis = analyzer.analyze_search_quality(search_term, results)
        
        logger.info(f"\n=== 검색 결과 분석 ===")
        logger.info(f"총 논문 수: {analysis['total_papers']}건")
        logger.info(f"관련 논문 수: {analysis['related_papers']}건")
        logger.info(f"검색 정확도: {analysis['relevance_rate']:.1f}%")
        logger.info(f"연도 범위: {analysis['year_range']}")
        logger.info(f"검색 소요 시간: {search_time:.1f}초")
        
        # 상위 논문 미리보기
        logger.info(f"\n=== 상위 논문 미리보기 (처음 5건) ===")
        for i, paper in enumerate(results[:5], 1):
            title = paper.get('title', 'N/A')
            # 관련 키워드 하이라이트
            if any(kw in title.lower() for kw in ['고용', '취업', '일자리', '채용']):
                title = f"🎯 {title}"
            
            logger.info(f"\n{i}. {title}")
            logger.info(f"   저자: {paper.get('author', 'N/A')}")
            logger.info(f"   기관: {paper.get('publisher', 'N/A')}")
            logger.info(f"   연도: {paper.get('pub_year', 'N/A')}")
        
        # DataFrame 생성
        df = pd.DataFrame(results)
        
        # Excel 내보내기
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"riss_improved_{search_term}_{timestamp}.xlsx"
        logger.info(f"\n💾 Excel 파일 저장 중: {filename}")
        analyzer.export_results(results, filename, search_term)
        
        logger.info(f"\n🎉 완료!")
        
    else:
        logger.warning("❌ 검색 결과가 없습니다.")


if __name__ == "__main__":
    main()