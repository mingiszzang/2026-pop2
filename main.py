import json
import re

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


st.set_page_config(
    page_title="전국 고령화 단계구분도",
    layout="wide",
)

POP_URL = (
    "https://raw.githubusercontent.com/greatsong/modudata/"
    "main/data/population_yearly.csv.gz"
)

GEO_URL = (
    "https://raw.githubusercontent.com/greatsong/modudata/"
    "main/data/boundaries/sigungu_kr.geojson"
)


@st.cache_data
def load_data():
    # 인구 데이터
    df = pd.read_csv(
        POP_URL,
        compression="gzip",
        dtype={"코드": str},
        low_memory=False,
    )

    # 시군구 경계 데이터
    response = requests.get(GEO_URL, timeout=60)
    response.raise_for_status()
    geojson = response.json()

    return df, geojson


def get_year(series):
    return pd.to_numeric(
        series.astype(str).str.extract(r"(\d{4})")[0],
        errors="coerce",
    )


def get_age(column):
    match = re.search(r"계_(\d+)세", column)
    return int(match.group(1)) if match else None


st.title("전국 고령화 단계구분도")
st.caption("2026년 6월 기준 시군구별 65세 이상 인구 비율")

with st.spinner("데이터를 불러오는 중입니다."):
    df, geojson = load_data()


# =========================================================
# 2026년 데이터 선택
# =========================================================
df["연도"] = get_year(df["연도"])
df = df[df["연도"] == 2026].copy()

# 행정동 코드 앞 5자리를 시군구 코드로 사용
df["코드"] = (
    df["코드"]
    .astype(str)
    .str.replace(r"\.0$", "", regex=True)
    .str.zfill(10)
)

df["시군구코드"] = df["코드"].str[:5]


# =========================================================
# 인구 열 선택
# =========================================================
total_cols = [
    col for col in df.columns
    if col.startswith("계_")
]

elderly_cols = [
    col for col in total_cols
    if get_age(col) is not None and get_age(col) >= 65
]

# 쉼표 등이 포함된 값을 숫자로 변환
df[total_cols] = (
    df[total_cols]
    .replace(",", "", regex=True)
    .apply(pd.to_numeric, errors="coerce")
    .fillna(0)
)

df["전체인구"] = df[total_cols].sum(axis=1)
df["고령인구"] = df[elderly_cols].sum(axis=1)


# =========================================================
# 시군구별 집계
# =========================================================
sigungu = (
    df.groupby("시군구코드", as_index=False)
    [["전체인구", "고령인구"]]
    .sum()
)

sigungu["고령화율"] = (
    sigungu["고령인구"]
    / sigungu["전체인구"]
    * 100
)


# =========================================================
# GeoJSON 코드 및 지역명 정리
# =========================================================
region_names = []

for feature in geojson["features"]:
    props = feature["properties"]

    code = str(props["코드"]).replace(".0", "").zfill(5)
    props["코드"] = code

    region_names.append(
        {
            "시군구코드": code,
            "시도": props["시도"],
            "시군구": props["시군구"],
        }
    )

region_names = pd.DataFrame(region_names)

sigungu = region_names.merge(
    sigungu,
    on="시군구코드",
    how="left",
)


# =========================================================
# 지도
# =========================================================
fig = px.choropleth(
    sigungu,
    geojson=geojson,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="고령화율",
    color_continuous_scale="Reds",
    custom_data=["시도", "시군구"],
    labels={"고령화율": "고령화율"},
)

fig.update_traces(
    marker_line_color="white",
    marker_line_width=0.4,
    hovertemplate=(
        "<b>%{customdata[0]} %{customdata[1]}</b><br>"
        "고령화율: %{z:.1f}%"
        "<extra></extra>"
    ),
)

fig.update_geos(
    fitbounds="locations",
    visible=False,
)

fig.update_layout(
    height=850,
    margin=dict(l=0, r=0, t=10, b=0),
    coloraxis_colorbar=dict(
        title="65세 이상<br>인구 비율",
        ticksuffix="%",
    ),
)

st.plotly_chart(
    fig,
    use_container_width=True,
    key="aging_map",
)


with st.expander("계산 방법"):
    st.markdown(
        """
- 행정동 코드의 앞 5자리로 시군구별 인구를 합산합니다.
- 전체 인구는 `계_`로 시작하는 모든 연령 열의 합입니다.
- 고령 인구는 `계_65세`부터 `계_100세 이상`까지의 합입니다.
- 고령화율은 다음과 같이 계산합니다.

```text
고령화율 = 65세 이상 인구 ÷ 전체 인구 × 100
    """
)
