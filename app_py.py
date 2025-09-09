import streamlit as st
import pandas as pd
import random
from pandasql import sqldf
import ollama

MODEL_NAME = "gemma3:12b"

# -----------------------------
# 매핑 파일 로더 (심플)
# -----------------------------
def load_mapping(file):
    mdf = pd.read_excel(file)
    if mdf.empty or len(mdf.columns) < 2:
        raise ValueError("매핑 파일은 최소 2개 컬럼(english, korean)이 필요합니다.")

    cols = {str(c).strip().lower(): c for c in mdf.columns}
    eng_key = cols.get("english") or cols.get("eng") or cols.get("en") or cols.get("영문") or cols.get("영문명")
    kor_key = cols.get("korean")  or cols.get("kor") or cols.get("ko") or cols.get("한글") or cols.get("한글명") or cols.get("alias") or cols.get("별칭")

    if eng_key is None or kor_key is None:
        eng_key, kor_key = mdf.columns[:2]

    ko2en = {}
    rows = []
    for _, r in mdf.iterrows():
        en = str(r[eng_key]).strip()
        ko = str(r[kor_key]).strip()
        if en and ko and en.lower() != "nan" and ko.lower() != "nan":
            ko2en[ko] = en
            rows.append({"korean": ko, "english": en})
    preview_df = pd.DataFrame(rows)
    return ko2en, preview_df

# -----------------------------
# NL → SQL (간단 프롬프트)
# -----------------------------
def convert_to_sql(nl_query, df, table_name="df"):
    schema_info = f"Columns: {', '.join(map(str, df.columns))}\n\nSample Data:\n{df.head(3).to_string(index=False)}"
    prompt = f"""
You convert Korean natural language into a valid SQLite SQL query for table "{table_name}".
Return only the SQL query (no backticks, no explanation).

Schema & sample:
{schema_info}

Natural language: "{nl_query}"
"""
    response = ollama.chat(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    sql_query = response["message"]["content"].strip()
    sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
    return sql_query

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="엑셀 당첨자 추출 (분기형)", layout="centered")
st.title("🎉 하나원큐 이벤트 당첨자 추출")

# 🔹 세션 기본값 (추첨 안정화에 필요)
if "filtered_df" not in st.session_state:
    st.session_state.filtered_df = pd.DataFrame()
if "winners" not in st.session_state:
    st.session_state.winners = pd.DataFrame()

# 1) 첫 화면에서 고객 엑셀과 매핑 엑셀 모두 업로더 표시
col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("이벤트 대상자 리스트 엑셀 업로드", type=["xlsx", "xls"], key="data")
with col2:
    mapping_file = st.file_uploader("(선택) 영문 컬럼 한글 매핑 엑셀 업로드 ", type=["xlsx", "xls"], key="mapping")

if uploaded_file is None:
    st.info("먼저 고객 데이터 엑셀을 업로드하세요.")
    st.stop()

try:
    base_df = pd.read_excel(uploaded_file)
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

st.subheader("📝 업로드된 데이터 미리보기")
st.dataframe(base_df.head())

# 매핑 처리
ko2en = {}
if mapping_file is not None:
    try:
        ko2en, mapping_preview = load_mapping(mapping_file)
        with st.expander("📖 영문 ↔ 한글 매핑 미리보기", expanded=False):
            st.dataframe(mapping_preview)
    except Exception as e:
        st.warning(f"매핑 로드 실패(무시하고 진행): {e}")
        ko2en = {}

# 2) 사용자 입력 칸 (요청 대기)
st.subheader("🔎 이벤트 선정 조건을 입력하세요")
nl_query = st.text_input("예: '가입횟수가 3회 이상이며 30대인 여성', '마케팅 동의했고, 급여가 인정된 고객'")
run = st.button("검색하기")

# 3) 사용자가 입력하면 '분기' 처리 → 🔸 여기서 세션에 filtered_df 저장
if run:
    if not nl_query.strip():
        st.warning("질의를 입력해 주세요.")
        st.stop()

    # 분기 1) 매핑 파일이 있으면: 한글 별칭 컬럼을 생성하여 접근 용이화
    if ko2en:
        df = base_df.copy()
        created_alias_cols = []
        for ko, en in ko2en.items():
            if en in df.columns and ko not in df.columns:
                df[ko] = df[en]
                created_alias_cols.append(ko)
        if created_alias_cols:
            st.info(f"매핑 적용: 한글 별칭 컬럼 추가 → {', '.join(created_alias_cols)}")
        else:
            st.info("매핑 적용: 추가된 별칭 컬럼 없음 (이미 존재하거나 매핑 대상 영문 컬럼이 데이터에 없음)")
        branch_used = "매핑 참조(별칭 컬럼 사용)"
    # 분기 2) 매핑 파일이 없으면: 업로드한 고객 엑셀의 컬럼만 참고
    else:
        df = base_df
        branch_used = "매핑 없음(원본 컬럼만 사용)"

    try:
        sql_query = convert_to_sql(nl_query, df, table_name="df")
        st.markdown(f"**실행 분기:** {branch_used}")
        st.markdown(f"➡️ 변환된 SQL\n```sql\n{sql_query}\n```")
        filtered_df = sqldf(sql_query, {"df": df})
    except Exception as e:
        st.error(f"쿼리 실행 오류: {e}")
        st.stop()

    if filtered_df.empty:
        st.warning("⚠️ 조건에 맞는 데이터가 없습니다. 다른 조건을 입력해보세요.")
        st.stop()

    # 🔹 핵심: rerun 대비, 결과를 세션에 저장
    st.session_state.filtered_df = filtered_df
    
    # 🔄 검색할 때마다 이전 추첨 결과 초기화
    st.session_state.winners = pd.DataFrame()

    st.subheader("📊 조건이 적용된 데이터")
    st.write(f"✅ 총 {len(filtered_df)}명이 조회되었습니다.")
    view_option = st.radio("데이터 표시 방식", ("상위 5개", "전체"), horizontal=True)
    st.dataframe(filtered_df.head() if view_option == "상위 5개" else filtered_df)

# 4) 추첨(항상 세션의 filtered_df 사용) → run=False여도 동작
df_for_draw = st.session_state.filtered_df

if not df_for_draw.empty:
    st.subheader("🎯 추첨")
    num_winners = st.number_input(
        "당첨자 수를 입력하세요",
        min_value=1,
        max_value=len(df_for_draw),
        value=1,
        step=1,
        key="num_winners"
    )

    if st.button("추첨하기", key="btn_draw"):
        st.session_state.winners = df_for_draw.sample(
            n=num_winners,
            random_state=random.randint(0, 10000)
        )

    winners = st.session_state.winners
    if not winners.empty:
        st.subheader("🏆 당첨자 명단")
        st.dataframe(winners)
        csv = winners.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 당첨자 명단 다운로드 (CSV)",
            data=csv,
            file_name="winners.csv",
            mime="text/csv",
            key="btn_download_winners"
        )
