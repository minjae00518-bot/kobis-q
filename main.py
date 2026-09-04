import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# 1. 웹 앱 기본 설정 (페이지 제목 및 넓은 레이아웃 설정)
st.set_page_config(
    page_title="어제 박스오피스 순위",
    page_icon="🎬",
    layout="wide"
)

# 2. 한국 표준시(KST: UTC+9) 기준으로 어제 날짜를 구하는 함수
def get_kst_yesterday():
    # 배포 서버의 시계와 무관하게 한국 시간 기준으로 현재 시각 구하기
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    # 오늘 데이터는 아직 집계 중이므로 어제 날짜 계산
    yesterday_kst = now_kst - timedelta(days=1)
    return yesterday_kst

# 3. KOBIS API 데이터 호출 함수 (@st.cache_data로 1시간 동안 결과 기억)
@st.cache_data(ttl=3600)
def fetch_box_office(api_key: str, target_date: str):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": api_key,
        "targetDt": target_date
    }
    
    try:
        # API 서버로 요청 보내기 (10초 응답 시간 제한)
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status() # HTTP 오류 발생 시 예외 처리
        data = response.json()
    except Exception as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"

    # KOBIS API 특성: 인증키 오류 시 status 200과 함께 faultInfo 객체 반환
    if "faultInfo" in data:
        msg = data["faultInfo"].get("message", "인증키 또는 요청 파라미터가 유효하지 않습니다.")
        return None, f"API 서비스 오류: {msg}"

    # JSON 데이터에서 영화 목록 추출
    box_office_result = data.get("boxOfficeResult", {})
    daily_list = box_office_result.get("dailyBoxOfficeList", [])

    if not daily_list:
        return None, "조회된 박스오피스 데이터가 없습니다."

    return daily_list, None

# --- 앱 화면 구성 시작 ---

# 어제 날짜 계산 및 문자열 형식 변환
yesterday_dt = get_kst_yesterday()
target_dt_str = yesterday_dt.strftime("%Y%m%d")      # API 조회용 (예: 20260903)
display_dt_str = yesterday_dt.strftime("%Y년 %m월 %d일") # 화면 표시용

st.title("🎬 일별 박스오피스 대시보드")
st.subheader(f"📅 {display_dt_str} 기준")

# 4. secrets에서 KOBIS API 키 존재 여부 확인
if "KOBIS_KEY" not in st.secrets or not st.secrets["KOBIS_KEY"]:
    st.error("⚠️ API 키(KOBIS_KEY)가 설정되지 않았습니다.")
    st.info(
        "**확인 및 조치 방법:**\n"
        "1. Streamlit Cloud 대시보드의 `App Settings > Secrets` 메뉴를 엽니다.\n"
        "2. `KOBIS_KEY = \"발급받은_키\"` 형태로 비밀 키를 등록했는지 확인하세요.\n"
        "3. 로컬 테스트 중이라면 `.streamlit/secrets.toml` 파일에 키를 추가했는지 확인하세요."
    )
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# 5. API 데이터 호출 실행 및 오류 확인
raw_data, error_msg = fetch_box_office(api_key, target_dt_str)

if error_msg:
    st.error(f"⚠️ 데이터를 가져올 수 없습니다: {error_msg}")
    st.warning(
        "**확인 및 조치 방법:**\n"
        "- 입력된 KOBIS API 키가 올바른지 확인하세요.\n"
        "- KOBIS 홈페이지에서 일일 호출 가능 횟수를 초과했는지 확인하세요.\n"
        "- KOBIS 서비스의 점검 시간인지 확인해 보세요."
    )
    st.stop()

# 6. 데이터를 데이터프레임으로 변환 및 숫자형 데이터 정제
df = pd.DataFrame(raw_data)

# 문자열 형태로 온 숫자 값들을 정수(int) 데이터 타입으로 변경
numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt"]
for col in numeric_columns:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

# 순위 기준으로 오름차순 정렬
df = df.sort_values("rank").reset_index(drop=True)

# 7. 1위 영화 지표 카드 3장(st.metric) 출력
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

# 8. 관객수 상위 5편 막대그래프 출력
st.markdown("### 📊 관객수 상위 5개 영화")
top_5_df = df.head(5)[["movieNm", "audiCnt"]].set_index("movieNm")
st.bar_chart(top_5_df)

st.divider()

# 9. 전체 순위 표(Table) 출력
st.markdown("### 📋 전체 박스오피스 순위")

# 원하는 열 선택 및 한글 열 이름으로 변경
display_df = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
display_df.columns = ["순위", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

# 표에 보여줄 숫자 값에 천 단위 쉼표(,) 서식 적용
formatted_df = display_df.copy()
formatted_df["관객수"] = formatted_df["관객수"].apply(lambda x: f"{x:,}")
formatted_df["누적관객"] = formatted_df["누적관객"].apply(lambda x: f"{x:,}")
formatted_df["스크린수"] = formatted_df["스크린수"].apply(lambda x: f"{x:,}")

st.dataframe(formatted_df, use_container_width=True, hide_index=True)
