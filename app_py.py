import streamlit as st
import pandas as pd
import random
from pandasql import sqldf
import ollama
MODEL_NAME="gemma3:12b"
# 자연어 → SQL 변환 (LLM + RAG)
def convert_to_sql(nl_query, df, table_name="df"):
    # 데이터 스키마 준비 (컬럼명 + 샘플 데이터 일부)
    schema_info = f"Columns: {', '.join(df.columns)}\n\nSample Data:\n{df.head(3).to_string(index=False)}"
    prompt = f"""
You are a helpful assistant that converts natural language into SQL queries.
The target table is named "{table_name}".
Here is the schema and sample data:
{schema_info}
Now, convert the following natural language request into a valid SQL query
that can be executed on this table:
Natural language: "{nl_query}"
Return only the SQL query.
"""
    response = ollama.chat(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    #sql_query = response.choices[0].message.content.strip()
    sql_query = response["message"]["content"].strip()
    sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
    return sql_query
# Streamlit UI
st.set_page_config(page_title="엑셀 당첨자 추첨기", layout="centered")
st.title(":짠: 엑셀 당첨자 추첨기")
# 엑셀 업로드
uploaded_file = st.file_uploader("엑셀 파일을 업로드하세요", type=["xlsx", "xls"])
if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)
    st.subheader(":메모: 업로드된 데이터 미리보기")
    st.dataframe(df.head())
    # 자연어 조건 입력
    st.subheader(":돋보기: 조건을 자연어로 입력하세요")
    nl_query = st.text_input("예: '나이가 30 이상인 사람만', '여자만'")
    filtered_df = df.copy()
    sql_query = None
    if nl_query:
        sql_query = convert_to_sql(nl_query, df, table_name="df")
        st.markdown(f":오른쪽을_가리키는_손_모양: 변환된 SQL 쿼리:\n```sql\n{sql_query}\n```")
        try:
            filtered_df = sqldf(sql_query, {"df": df})
            st.subheader(":막대_차트: 조건이 적용된 데이터")
            # :흰색_확인_표시: 조회된 총 인원 수 표시
            st.write(f":흰색_확인_표시: 총 {len(filtered_df)}명이 조회되었습니다.")
            # :흰색_확인_표시: 데이터 표시 옵션 선택
            view_option = st.radio(
                "데이터 표시 방식 선택",
                ("상위 5개만 보기", "전체 보기"),
                horizontal=True
            )
            if view_option == "상위 5개만 보기":
                st.dataframe(filtered_df.head())
            else:
                st.dataframe(filtered_df)
        except Exception as e:
            st.error(f"쿼리 실행 오류: {e}")
    # 추첨 인원 입력
    if not filtered_df.empty:
        num_winners = st.number_input(
            "당첨자 수를 입력하세요",
            min_value=1,
            max_value=len(filtered_df),
            value=1,
            step=1
        )
        if st.button("추첨하기"):
            winners = filtered_df.sample(n=num_winners, random_state=random.randint(0, 10000))
            st.subheader(":트로피: 당첨자 명단")
            st.dataframe(winners)
            csv = winners.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label=":받은_편지함_트레이: 당첨자 명단 다운로드 (CSV)",
                data=csv,
                file_name="winners.csv",
                mime="text/csv",
            )
    else:
        st.warning(":경고: 조건에 맞는 데이터가 없습니다. 다른 조건을 입력해보세요.")