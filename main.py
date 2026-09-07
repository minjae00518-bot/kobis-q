import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# 1. 웹 앱 기본 설정 (페이지 제목 및 넓은 레이아웃)
st.set_page_config(
    page_title="일별 박스오피스 조회",
    page_icon="🎬",
    layout="wide"
)

# 2. 한국 표준시(KST: UTC+9) 기준으로 어제 날짜를 구하는 함수
def get_kst_yesterday():
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    # 오늘 데이터는 아직 집계 전이므로 가장 최근 가능 날짜는 어제
    return (now_kst - timedelta(days=1)).date()

# 기준 어제 날짜 구하기
yesterday = get_kst_yesterday()

# --- 화면 상단 타이틀 및 달력 날짜 선택 ---
st.title("🎬 일별 박스오피스 대시보드")

# 3. 달력(st.date_input)으로 날짜 선택
# max_value를 어제 날짜로 지정하여 오늘 이후 날짜 선택 방지
selected_date = st.date_input(
    "📅 조회할 날짜를 선택하세요 (어제 날짜까지만 선택 가능)",
    value=yesterday,
    max_value=yesterday,
    min_value=datetime(2004, 1, 1).date()
)

# 선택한 날짜를 API 형식(YYYYMMDD)과 화면 표시용 형식으로 각각 변환
target_dt_str = selected_date.strftime("%Y%m%d")
display_dt_str = selected_date.strftime("%Y년 %m월 %d일")

st.subheader(f"📌 {display_dt_str} 기준 박스오피스")

# 4. KOBIS API 데이터 호출 함수 (@st.cache_data로 동일 날짜 결과는 1시간 캐싱)
@st.cache_data(ttl=3600)
def fetch_box_office(api_key: str, target_date: str):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": api_key,
        "targetDt": target_date
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"

    # KOBIS API 오류 예외 처리 (인증키 오류 등)
    if "faultInfo" in data:
        msg = data["faultInfo"].get("message", "인증키 또는 요청 파라미터가 유효하지 않습니다.")
        return None, f"API 서비스 오류: {msg}"

    box_office_result = data.get("boxOfficeResult", {})
    daily_list = box_office_result.get("dailyBoxOfficeList", [])

    # 선택한 날짜의 영화 목록이 비어있는 경우
    if not daily_list:
        return None, "empty"

    return daily_list, None

# 5. Secrets 키 존재 여부 확인
if "KOBIS_KEY" not in st.secrets or not st.secrets["KOBIS_KEY"]:
    st.error("⚠️ API 키(KOBIS_KEY)가 설정되지 않았습니다.")
    st.info(
        "**확인 및 조치 방법:**\n"
        "1. Streamlit Cloud 대시보드의 `App Settings > Secrets` 메뉴를 엽니다.\n"
        "2. `KOBIS_KEY = \"발급받은_키\"` 형태로 등록했는지 확인하세요.\n"
        "3. 로컬 테스트 시 `.streamlit/secrets.toml` 파일에 키를 추가해 주세요."
    )
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# 6. 선택한 날짜의 API 데이터 호출 실행
raw_data, error_code = fetch_box_office(api_key, target_dt_str)

# 영화 목록이 비어있거나 에러가 난 경우 안내
if error_code == "empty":
    st.warning("⚠️ 그날은 아직 집계 전입니다.")
    st.stop()
elif error_code:
    st.error(f"⚠️ 데이터를 가져올 수 없습니다: {error_code}")
    st.warning(
        "**확인 및 조치 방법:**\n"
        "- 입력된 KOBIS API 키가 올바른지 확인하세요.\n"
        "- KOBIS 홈페이지에서 일일 호출 가능 횟수를 초과했는지 확인하세요."
    )
    st.stop()

# 7. 데이터프레임 변환 및 숫자형 데이터 정제
df = pd.DataFrame(raw_data)

# 문자열로 들어온 정수 데이터들을 숫자로 변환
numeric_columns = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt"]
for col in numeric_columns:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

# 기본 순위 정렬 (1위 ~ 10위)
df = df.sort_values("rank").reset_index(drop=True)

# 8. 1위 영화 지표 카드 3장 출력
top_1 = df.iloc[0]
st.markdown(f"### 🏆 1위 영화: **{top_1['movieNm']}**")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="당일 관객수", value=f"{top_1['audiCnt']:,} 명")
with col2:
    st.metric(label="누적 관객수", value=f"{top_1['audiAcc']:,} 명")
with col3:
    st.metric(label="상영 스크린수", value=f"{top_1['scrnCnt']:,} 개")

st.divider()

# 9. 관객수 상위 5편 막대그래프 (1위~5위 순서 고정)
st.markdown("### 📊 관객수 상위 5개 영화 (순위순)")

top_5_df = df.head(5).copy()
top_5_df["rank_label"] = top_5_df.apply(lambda row: f"{row['rank']}위. {row['movieNm']}", axis=1)

chart_df = top_5_df[["rank_label", "audiCnt"]].rename(columns={"audiCnt": "당일 관객수"}).set_index("rank_label")
st.bar_chart(chart_df)

st.divider()

# 10. 순위 증감(rankInten) 및 누적 관객 100만 명 이상 트로피 서식 가공

# 전날 대비 순위 증감 기호 부여 함수 (양수: 빨간 위 화살표 / 음수: 파란 아래 화살표)
def format_rank_change(val):
    if val > 0:
        return f"🔺 {val}"
    elif val < 0:
        return f"🔹 {abs(val)}"
    else:
        return "-"

df["rank_change"] = df["rankInten"].apply(format_rank_change)

# 누적관객이 100만 명 이상(>= 1,000,000)인 영화는 영화명 옆에 🏆 붙이기
def format_movie_name(row):
    name = row["movieNm"]
    if row["audiAcc"] >= 1_000_000:
        return f"{name} 🏆"
    return name

df["formatted_movie_nm"] = df.apply(format_movie_name, axis=1)

# 11. 전체 순위 표(Table) 출력 및 정렬 옵션 설정
st.markdown("### 📋 전체 박스오피스 순위")

col_sort1, col_sort2 = st.columns(2)

with col_sort1:
    sort_target = st.selectbox(
        "📊 정렬할 항목 선택",
        options=["당일 관객수", "누적 관객수", "스크린수"]
    )

with col_sort2:
    sort_order = st.radio(
        "⬆️⬇️ 정렬 순서 선택",
        options=["많은 순 (1위부터)", "적은 순 (10위부터)"],
        horizontal=True
    )

# 선택한 옵션에 따라 데이터 정렬 수행
target_col_map = {
    "당일 관객수": "audiCnt",
    "누적 관객수": "audiAcc",
    "스크린수": "scrnCnt"
}
selected_col = target_col_map[sort_target]
is_ascending = (sort_order == "적은 순 (10위부터)")

df_sorted = df.sort_values(by=selected_col, ascending=is_ascending).reset_index(drop=True)

# 정렬된 순서에 맞춰 '1위', '2위' 형태의 순위 표시열 재생성
df_sorted["rank_display"] = [f"{i}위" for i in range(1, len(df_sorted) + 1)]

display_df = df_sorted[["rank_display", "rank_change", "formatted_movie_nm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
display_df.columns = ["순위", "전날 대비", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

# 천 단위 쉼표 서식 적용
display_df["관객수"] = display_df["관객수"].apply(lambda x: f"{x:,}")
display_df["누적관객"] = display_df["누적관객"].apply(lambda x: f"{x:,}")
display_df["스크린수"] = display_df["스크린수"].apply(lambda x: f"{x:,}")

# HTML 테이블 방식으로 출력하여 헤더 클릭에 의한 순위 흐트러짐 방지 및 '순위' 열 표시
table_html = display_df.to_html(index=False, justify="center")

css = """
<style>
.stTableContainer table {
    width: 100%;
    border-collapse: collapse;
    font-size: 15px;
    margin-top: 10px;
}
.stTableContainer th {
    background-color: var(--background-secondary-color, #f0f2f6);
    color: var(--text-color, #31333F);
    font-weight: 600;
    padding: 12px;
    border-bottom: 2px solid #ccc;
    text-align: center !important;
}
.stTableContainer td {
    padding: 10px;
    border-bottom: 1px solid #eee;
    text-align: center !important;
}
</style>
"""

st.markdown(f"{css}<div class='stTableContainer'>{table_html}</div>", unsafe_allow_html=True)
