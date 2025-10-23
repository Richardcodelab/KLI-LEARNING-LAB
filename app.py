# -*- coding: utf-8 -*-
"""
Streamlit 통합 앱 (MVP)
- 검색어 정규화 (CSV + AI 옵션)
- KCI & RISS 검색 실행
- 결과 병합/중복제거/필터링/다운로드
- 기본 분석 탭 (연도/소스/학술지)

필수 파일: query_normalizer.py, KCI_collector.py, RISS_collector.py, keyword_mapping.csv, .env
실행: streamlit run app.py
"""

import os
import io
import re
import time
from datetime import datetime
from typing import List, Optional

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

import streamlit as st
from dotenv import load_dotenv

# 내부 모듈
from query_normalizer import QueryNormalizer
from KCI_collector import OptimizedKCIAnalyzer
from RISS_collector import ImprovedRISSAnalyzer

# --- 초기 설정 ---
st.set_page_config(page_title="러닝랩 선행연구 자동분류기", layout="wide")
load_dotenv()  # .env 로드

KCI_API_KEY = os.getenv("KCI_API_KEY", "")
RISS_API_KEY = os.getenv("RISS_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# --- 유틸 ---

def normalize_title(t: str) -> str:
    if not isinstance(t, str):
        return ""
    # 공백/특수문자 제거, 소문자화
    t = re.sub(r"\s+", " ", t).strip().lower()
    t = re.sub(r"[^0-9a-z가-힣 ]", "", t)
    return t


def to_excel_bytes(df: pd.DataFrame, sheets: Optional[dict] = None) -> bytes:
    """DataFrame 또는 복수 시트 엑셀 바이트 생성"""
    data = io.BytesIO()
    with pd.ExcelWriter(data, engine="openpyxl") as writer:
        if sheets:
            for name, d in sheets.items():
                d.to_excel(writer, sheet_name=name[:31], index=False)
        else:
            df.to_excel(writer, sheet_name="results", index=False)
    data.seek(0)
    return data.read()


def merge_frames(df_kci: Optional[pd.DataFrame], df_riss: Optional[pd.DataFrame]) -> pd.DataFrame:
    frames = []
    # KCI 표준화
    if df_kci is not None and not df_kci.empty:
        kci = df_kci.copy()
        kci["source"] = "KCI"
        # 표준 스키마 매핑
        kci.rename(
            columns={
                "journal_name": "venue",
                "authors": "authors",
                "pub_year": "pub_year",
                "title": "title",
                "url": "url",
                "doi": "doi",
                "abstract": "abstract",
                "keywords": "keywords",
            },
            inplace=True,
        )
        # 누락 컬럼 보강
        for col in ["authors", "venue", "pub_year", "url", "doi", "abstract", "keywords"]:
            if col not in kci.columns:
                kci[col] = ""
        frames.append(kci[[
            "title", "authors", "venue", "pub_year", "url", "doi", "abstract", "keywords", "source"
        ]])

    # RISS 표준화
    if df_riss is not None and not df_riss.empty:
        riss = df_riss.copy()
        riss["source"] = "RISS"
        # RISS_collector 스키마 참고
        # title, author, publisher, pub_year, doc_type, material_type, url, has_abstract ...
        riss.rename(
            columns={
                "author": "authors",
                "publisher": "venue",
            },
            inplace=True,
        )
        # 보강 컬럼
        for col in ["doi", "abstract", "keywords"]:
            if col not in riss.columns:
                riss[col] = ""
        # 표준 컬럼만 정렬
        keep = ["title", "authors", "venue", "pub_year", "url", "doi", "abstract", "keywords", "source", "doc_type", "material_type"]
        for c in keep:
            if c not in riss.columns:
                riss[c] = ""
        frames.append(riss[keep])

    if not frames:
        return pd.DataFrame(columns=["title", "authors", "venue", "pub_year", "url", "doi", "abstract", "keywords", "source"])  # empty

    all_df = pd.concat(frames, ignore_index=True)

    # 타입 보정
    all_df["pub_year"] = all_df["pub_year"].astype(str).str.extract(r"(\d{4})")[0]

    # 중복 제거 (우선 DOI, 그다음 제목 정규화)
    before = len(all_df)
    if "doi" in all_df.columns:
        all_df = all_df.drop_duplicates(subset=["doi"]).reset_index(drop=True)
    # DOI가 비어있는 경우를 대비해 제목 키 생성
    all_df["_title_key"] = all_df["title"].apply(normalize_title)
    all_df = all_df.drop_duplicates(subset=["_title_key"]).drop(columns=["_title_key"]).reset_index(drop=True)
    after = len(all_df)

    st.caption(f"🧹 중복 제거: {before - after}건 제거, 최종 {after}건")
    return all_df


# --- 사이드바 ---
st.sidebar.title("⚙️ 옵션")
use_ai = st.sidebar.checkbox("AI로 검색어 확장 사용", value=bool(OPENAI_API_KEY))
source_kci = st.sidebar.checkbox("KCI 사용", value=True)
source_riss = st.sidebar.checkbox("RISS 사용", value=True)

col1, col2 = st.sidebar.columns(2)
with col1:
    start_year = st.number_input("시작연도", min_value=1900, max_value=2100, value=2018)
with col2:
    end_year = st.number_input("종료연도", min_value=1900, max_value=2100, value=2025)

kci_fetch_details = st.sidebar.checkbox("KCI 상세조회(초록/키워드 보강)", value=True)
riss_doc_type = st.sidebar.selectbox("RISS 자료유형", options=["T(학위)", "A(국내학술)", "F(해외학술)", "혼합"], index=0)
max_riss = st.sidebar.slider("RISS 최대 결과 수", min_value=50, max_value=500, value=200, step=50)

# --- 메인 영역 ---
st.title("🔎 선행연구 자동분류기 (MVP)")
st.write("KCI/RISS를 통합해 자연어로 선행연구를 빠르게 수집하고 정제합니다.")

query = st.text_input("검색어를 입력하세요", placeholder="예) 청년에게 신용 제약이 미치는 영향")
run = st.button("검색 실행", type="primary")

if run:
    if not query.strip():
        st.warning("검색어를 입력해 주세요.")
        st.stop()

    # --- 검색어 정규화 ---
    with st.spinner("검색어 정규화 중…"):
        try:
            normalizer = QueryNormalizer(
                csv_path="keyword_mapping.csv",
                use_ai=use_ai and bool(OPENAI_API_KEY),
                model="gpt-3.5-turbo",
            )
            # query_normalizer.py 버전 호환 (구버전: normalize(query), 신버전: normalize(query, max_total=..., include_original=...))
            try:
                terms = normalizer.normalize(query, max_total=10, include_original=True)
            except TypeError:
                # 구버전 시그니처 호환
                terms = normalizer.normalize(query)
        except Exception as e:
            st.error(f"검색어 정규화 실패: {e}")
            terms = [query]

    st.success("정규화된 키워드")
    st.write(terms)

    primary_term = terms[0] if terms else query

    # --- 데이터 수집 ---
    df_kci = pd.DataFrame()
    df_riss = pd.DataFrame()

    # KCI
    if source_kci:
        if not KCI_API_KEY:
            st.warning("KCI_API_KEY가 .env에 없습니다. KCI 검색을 건너뜁니다.")
        else:
            with st.spinner("KCI 검색 중…"):
                try:
                    kci = OptimizedKCIAnalyzer(api_key=KCI_API_KEY)
                    kci_result = kci.search_articles(
                        title=primary_term,
                        date_from=f"{int(start_year)}01",
                        date_to=f"{int(end_year)}12",
                        page=1,
                        display_count=50,
                    )
                    df_kci = kci.extract_article_info_optimized(kci_result, fetch_details=kci_fetch_details)
                    st.success(f"KCI 결과: {len(df_kci)}건")
                except Exception as e:
                    st.error(f"KCI 검색 실패: {e}")

    # RISS
    if source_riss:
        if not RISS_API_KEY:
            st.warning("RISS_API_KEY가 .env에 없습니다. RISS 검색을 건너뜁니다.")
        else:
            with st.spinner("RISS 검색 중…"):
                try:
                    riss = ImprovedRISSAnalyzer(api_key=RISS_API_KEY)
                    dtype_map = {
                        "T(학위)": "T",
                        "A(국내학술)": "A",
                        "F(해외학술)": "F",
                        "혼합": None,
                    }
                    dtype = dtype_map.get(riss_doc_type)

                    results = []
                    if dtype is None:
                        for t in ["T", "A", "F"]:
                            results.extend(
                                riss.search_with_multiple_strategies(
                                    primary_term, doc_type=t, start_year=int(start_year), end_year=int(end_year), max_results=max_riss
                                )
                            )
                            time.sleep(0.2)
                    else:
                        results = riss.search_with_multiple_strategies(
                            primary_term, doc_type=dtype, start_year=int(start_year), end_year=int(end_year), max_results=max_riss
                        )
                    df_riss = riss.create_dataframe(results)
                    st.success(f"RISS 결과: {len(df_riss)}건")
                except Exception as e:
                    st.error(f"RISS 검색 실패: {e}")

    if (df_kci is None or df_kci.empty) and (df_riss is None or df_riss.empty):
        st.info("검색 결과가 없습니다. 키워드를 더 일반적으로 변경하거나 연도 범위를 넓혀보세요.")
        st.stop()

    # --- 병합/중복 제거 ---
    with st.spinner("결과 병합 및 중복 제거…"):
        merged = merge_frames(df_kci, df_riss)

    # --- 필터 UI ---
    st.subheader("결과 미리보기")
    with st.expander("필터", expanded=True):
        colf1, colf2, colf3 = st.columns(3)
        with colf1:
            src_filter = st.multiselect("소스", options=sorted(merged["source"].dropna().unique().tolist()), default=sorted(merged["source"].dropna().unique().tolist()))
        with colf2:
            years = sorted([y for y in merged["pub_year"].dropna().unique().tolist() if isinstance(y, str)])
            year_filter = st.multiselect("연도", options=years, default=years)
        with colf3:
            text_filter = st.text_input("제목/저자 포함 키워드")

    view = merged.copy()
    if src_filter:
        view = view[view["source"].isin(src_filter)]
    if year_filter:
        view = view[view["pub_year"].astype(str).isin([str(y) for y in year_filter])]
    if text_filter.strip():
        ql = text_filter.lower().strip()
        view = view[
            view["title"].fillna("").str.lower().str.contains(ql)
            | view["authors"].fillna("").str.lower().str.contains(ql)
        ]

    st.dataframe(view.reset_index(drop=True), use_container_width=True, height=420)

    # --- 다운로드 ---
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "📥 CSV 다운로드",
            data=view.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"results_{normalize_title(primary_term)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
    with c2:
        xls = to_excel_bytes(view)
        st.download_button(
            "📊 Excel 다운로드",
            data=xls,
            file_name=f"results_{normalize_title(primary_term)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with c3:
        st.write("")

    # --- 분석 탭 ---
    tab1, tab2, tab3 = st.tabs(["연도별 분포", "소스별 분포", "학술지/기관 Top 15"])

    with tab1:
        st.subheader("연도별 논문 수")
        ycnt = (
            view.assign(pub_year=view["pub_year"].astype(str).str.extract(r"(\d{4})")[0])
            .dropna(subset=["pub_year"]) 
            .groupby("pub_year").size()
        )
        if not ycnt.empty:
            fig = plt.figure()
            ycnt.sort_index().plot(kind="bar")
            plt.xlabel("연도")
            plt.ylabel("논문 수")
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("연도 정보가 충분하지 않습니다.")

    with tab2:
        st.subheader("소스별 논문 수")
        scnt = view.groupby("source").size()
        if not scnt.empty:
            fig = plt.figure()
            scnt.plot(kind="bar")
            plt.xlabel("소스")
            plt.ylabel("논문 수")
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("소스 정보가 없습니다.")

    with tab3:
        st.subheader("학술지/기관 상위 15")
        if "venue" in view.columns and not view["venue"].dropna().empty:
            vcnt = (
                view["venue"].fillna("").replace("", np.nan).dropna().value_counts().head(15)
            )
            if not vcnt.empty:
                fig = plt.figure()
                vcnt.sort_values(ascending=True).plot(kind="barh")
                plt.xlabel("논문 수")
                plt.ylabel("학술지/기관")
                plt.tight_layout()
                st.pyplot(fig)
            else:
                st.info("표시할 학술지/기관 데이터가 없습니다.")
        else:
            st.info("학술지/기관 컬럼이 없습니다.")

else:
    st.info("좌측 옵션을 확인하고, 검색어를 입력한 뒤 '검색 실행'을 눌러주세요.")
