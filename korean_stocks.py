import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(
    page_title="국내 주식 대시보드",
    page_icon="📈",
    layout="wide",
)

STOCKS = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "LG에너지솔루션": "373220.KS",
    "삼성바이오로직스": "207940.KS",
    "현대차": "005380.KS",
    "기아": "000270.KS",
    "NAVER": "035420.KS",
    "카카오": "035720.KS",
    "셀트리온": "068270.KS",
    "POSCO홀딩스": "005490.KS",
}

PERIOD_OPTIONS = {
    "1개월": "1mo",
    "3개월": "3mo",
    "6개월": "6mo",
    "1년": "1y",
    "2년": "2y",
}

# ── 사이드바 ──────────────────────────────────────────────
st.sidebar.title("⚙️ 설정")

selected_names = st.sidebar.multiselect(
    "종목 선택",
    options=list(STOCKS.keys()),
    default=list(STOCKS.keys()),
)

period_label = st.sidebar.selectbox("조회 기간", list(PERIOD_OPTIONS.keys()), index=2)
period = PERIOD_OPTIONS[period_label]

chart_type = st.sidebar.radio("차트 유형", ["캔들스틱", "라인"])

# ── 데이터 로드 ────────────────────────────────────────────
def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance MultiIndex 컬럼을 단일 레벨로 변환"""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df

@st.cache_data(ttl=300)
def load_data(tickers: list[str], period: str) -> dict[str, pd.DataFrame]:
    data = {}
    for name, ticker in tickers:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if not df.empty:
            data[name] = flatten_columns(df)
    return data

@st.cache_data(ttl=300)
def load_info(tickers: list[str]) -> dict:
    info = {}
    for name, ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info[name] = t.info
        except Exception:
            info[name] = {}
    return info

selected_pairs = [(n, STOCKS[n]) for n in selected_names]

if not selected_names:
    st.warning("사이드바에서 종목을 하나 이상 선택하세요.")
    st.stop()

with st.spinner("데이터 수집 중..."):
    stock_data = load_data(selected_pairs, period)
    stock_info = load_info(selected_pairs)

# ── 헤더 ──────────────────────────────────────────────────
st.title("📈 국내 주식 대시보드")
st.caption(f"데이터 기준: yfinance  |  조회 기간: {period_label}  |  마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ── 요약 카드 ──────────────────────────────────────────────
st.subheader("종목 현황")
cols = st.columns(min(len(selected_names), 5))
for i, name in enumerate(selected_names):
    col = cols[i % 5]
    df = stock_data.get(name)
    if df is None or df.empty:
        col.metric(name, "N/A")
        continue

    close = df["Close"].squeeze()  # Series 보장
    latest = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else latest
    change_pct = (latest - prev) / prev * 100

    col.metric(
        label=name,
        value=f"₩{latest:,.0f}",
        delta=f"{change_pct:+.2f}%",
    )

st.divider()

# ── 개별 주가 차트 ─────────────────────────────────────────
st.subheader("주가 차트")

tab_names = [n for n in selected_names if n in stock_data]
tabs = st.tabs(tab_names)

for tab, name in zip(tabs, tab_names):
    df = stock_data[name]
    with tab:

        fig = go.Figure()
        if chart_type == "캔들스틱":
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df["Open"], high=df["High"],
                low=df["Low"], close=df["Close"],
                name=name,
                increasing_line_color="#e74c3c",
                decreasing_line_color="#3498db",
            ))
        else:
            fig.add_trace(go.Scatter(
                x=df.index, y=df["Close"],
                mode="lines", name=name,
                line=dict(width=2, color="#e74c3c"),
            ))
            # 이동평균선
            for window, color in [(20, "#f39c12"), (60, "#9b59b6")]:
                if len(df) >= window:
                    ma = df["Close"].rolling(window).mean()
                    fig.add_trace(go.Scatter(
                        x=df.index, y=ma,
                        mode="lines", name=f"MA{window}",
                        line=dict(width=1.2, dash="dot", color=color),
                    ))

        fig.update_layout(
            title=f"{name} 주가 ({period_label})",
            xaxis_title="날짜",
            yaxis_title="가격 (KRW)",
            xaxis_rangeslider_visible=False,
            height=420,
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

        # 거래량
        vol_fig = go.Figure(go.Bar(
            x=df.index, y=df["Volume"],
            marker_color="#3498db", opacity=0.7, name="거래량",
        ))
        vol_fig.update_layout(
            title="거래량",
            height=180,
            template="plotly_dark",
            margin=dict(t=30, b=20),
        )
        st.plotly_chart(vol_fig, use_container_width=True)

st.divider()

# ── 수익률 비교 ────────────────────────────────────────────
st.subheader("기간 누적 수익률 비교")

returns_df = pd.DataFrame()
for name in tab_names:
    df = stock_data[name]
    close = df["Close"].dropna()
    if len(close) > 0:
        returns_df[name] = (close / close.iloc[0] - 1) * 100

if not returns_df.empty:
    ret_fig = px.line(
        returns_df,
        labels={"value": "누적 수익률 (%)", "index": "날짜", "variable": "종목"},
        template="plotly_dark",
        height=400,
    )
    ret_fig.update_layout(hovermode="x unified")
    st.plotly_chart(ret_fig, use_container_width=True)

st.divider()

# ── 통계 테이블 ────────────────────────────────────────────
st.subheader("기간 통계")

rows = []
for name in tab_names:
    df = stock_data[name]
    close = df["Close"].dropna()
    if len(close) == 0:
        continue
    daily_ret = close.pct_change().dropna()
    rows.append({
        "종목": name,
        "현재가 (₩)": f"{close.iloc[-1]:,.0f}",
        "최고가 (₩)": f"{close.max():,.0f}",
        "최저가 (₩)": f"{close.min():,.0f}",
        "기간 수익률": f"{(close.iloc[-1]/close.iloc[0]-1)*100:+.2f}%",
        "일 변동성 (σ)": f"{daily_ret.std()*100:.2f}%",
        "평균 거래량": f"{df['Volume'].mean():,.0f}",
    })

if rows:
    stat_df = pd.DataFrame(rows).set_index("종목")
    st.dataframe(stat_df, use_container_width=True)
