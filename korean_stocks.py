import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from openai import OpenAI

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

# API Key 입력
st.sidebar.subheader("🤖 ChatGPT 설정")
api_key = st.sidebar.text_input(
    "OpenAI API Key",
    type="password",
    placeholder="sk-...",
    help="OpenAI API 키를 입력하세요. 키는 저장되지 않습니다.",
)

st.sidebar.divider()

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

# ── 챗봇용 주식 데이터 요약 생성 ───────────────────────────
def build_stock_summary(stock_data: dict, period_label: str) -> str:
    lines = [f"아래는 현재 조회 중인 국내 주식 데이터입니다. (조회 기간: {period_label})\n"]
    for name, df in stock_data.items():
        close = df["Close"].squeeze().dropna()
        if len(close) == 0:
            continue
        daily_ret = close.pct_change().dropna()
        latest = float(close.iloc[-1])
        prev   = float(close.iloc[-2]) if len(close) > 1 else latest
        high   = float(close.max())
        low    = float(close.min())
        ret    = (latest / float(close.iloc[0]) - 1) * 100
        vol    = float(df["Volume"].mean())
        lines.append(
            f"- {name}: 현재가 {latest:,.0f}원 | 전일대비 {(latest-prev)/prev*100:+.2f}% | "
            f"기간수익률 {ret:+.2f}% | 최고가 {high:,.0f}원 | 최저가 {low:,.0f}원 | "
            f"평균거래량 {vol:,.0f}주 | 일변동성 {daily_ret.std()*100:.2f}%"
        )
    return "\n".join(lines)

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

    close = df["Close"].squeeze()
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

        vol_fig = go.Figure(go.Bar(
            x=df.index, y=df["Volume"],
            marker_color="#3498db", opacity=0.7, name="거래량",
        ))
        vol_fig.update_layout(
            title="거래량", height=180,
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

st.divider()

# ── AI 챗봇 ───────────────────────────────────────────────
st.subheader("🤖 AI 주식 분석 챗봇")

if not api_key:
    st.info("왼쪽 사이드바에서 OpenAI API Key를 입력하면 챗봇을 사용할 수 있습니다.")
else:
    # 대화 기록 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []

    stock_summary = build_stock_summary(stock_data, period_label)

    SYSTEM_PROMPT = f"""당신은 주식 데이터를 분석해주는 전문 AI 어시스턴트입니다.
사용자가 현재 보고 있는 국내 주식 데이터를 바탕으로 질문에 답변해주세요.
투자 권유는 하지 않으며, 데이터 기반의 객관적인 분석을 제공합니다.
답변은 한국어로 해주세요.

{stock_summary}"""

    # 대화 내역 출력
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 빠른 질문 버튼
    st.write("**빠른 질문:**")
    quick_cols = st.columns(4)
    quick_questions = [
        "가장 수익률이 높은 종목은?",
        "가장 변동성이 큰 종목은?",
        "전체 종목 요약 분석해줘",
        "거래량이 가장 많은 종목은?",
    ]
    for i, q in enumerate(quick_questions):
        if quick_cols[i].button(q, use_container_width=True):
            st.session_state.quick_input = q
            st.rerun()

    # 빠른 질문 처리
    user_input = st.session_state.pop("quick_input", None)

    # 채팅 입력
    chat_input = st.chat_input("주식에 대해 무엇이든 물어보세요...")
    if chat_input:
        user_input = chat_input

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("분석 중..."):
                try:
                    client = OpenAI(api_key=api_key)
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            *st.session_state.messages,
                        ],
                        temperature=0.7,
                        max_tokens=1000,
                    )
                    answer = response.choices[0].message.content
                except Exception as e:
                    answer = f"오류가 발생했습니다: {str(e)}"

            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})

    # 대화 초기화 버튼
    if st.session_state.get("messages"):
        if st.button("대화 초기화", type="secondary"):
            st.session_state.messages = []
            st.rerun()
