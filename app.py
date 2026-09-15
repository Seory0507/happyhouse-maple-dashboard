import os
import re
import base64
import html
from io import BytesIO
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv


# =========================================================
# 기본 설정
# =========================================================
load_dotenv()

st.set_page_config(
    page_title="해피하우스 캐릭터 목록",
    page_icon="🍁",
    layout="wide",
)


# =========================================================
# 설정값
# 로컬 = .env
# 배포 = Streamlit Secrets
# =========================================================
def get_config(key, default=""):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    return os.getenv(key, default)


SHEET_URL = get_config("SHEET_URL")
SHEET_NAME = get_config("SHEET_NAME", "캐릭터목록")
APP_PASSWORD = get_config("APP_PASSWORD")


# =========================================================
# 비밀번호 인증
# =========================================================
def check_password():
    if "password_ok" not in st.session_state:
        st.session_state.password_ok = False

    if st.session_state.password_ok:
        return True

    st.markdown(
        """
<style>
.stApp {
    background:
        radial-gradient(
            circle at top,
            #162032 0%,
            #0c111a 42%,
            #080c13 100%
        );
}

.block-container {
    max-width: 520px;
    padding-top: 10rem;
}

.login-title {
    text-align: center;
    color: #f4f7ff;
    font-size: 2rem;
    font-weight: 900;
    margin-bottom: 2rem;
}
</style>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="login-title">'
        '🍁 해피하우스 캐릭터 목록'
        '</div>',
        unsafe_allow_html=True
    )

    password = st.text_input(
        "비밀번호",
        type="password",
        placeholder="비밀번호를 입력하세요"
    )

    if st.button(
        "입장",
        use_container_width=True
    ):
        if not APP_PASSWORD:
            st.error("앱 비밀번호가 설정되어 있지 않습니다.")

        elif password == APP_PASSWORD:
            st.session_state.password_ok = True
            st.rerun()

        else:
            st.error("비밀번호가 틀렸습니다.")

    return False


if not check_password():
    st.stop()


# =========================================================
# 구글 시트 ID
# =========================================================
def get_sheet_id(sheet_url):
    if not sheet_url:
        return None

    try:
        return sheet_url.split("/d/")[1].split("/")[0]
    except IndexError:
        return None


# =========================================================
# Google Drive 파일 ID
# =========================================================
def get_drive_file_id(url):
    if not url:
        return None

    url = str(url).strip()

    match = re.search(r"/file/d/([^/]+)", url)
    if match:
        return match.group(1)

    match = re.search(r"[?&]id=([^&]+)", url)
    if match:
        return match.group(1)

    return None


# =========================================================
# 이미지 다운로드
# 대표이미지 + 보스배율 캡처 공용
# =========================================================
@st.cache_data(ttl=300)
def load_image_bytes(url):
    if not url:
        return None

    file_id = get_drive_file_id(url)

    try:
        if file_id:
            download_url = (
                f"https://drive.google.com/uc"
                f"?export=download&id={file_id}"
            )
        else:
            download_url = url

        response = requests.get(
            download_url,
            timeout=20,
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            ""
        ).lower()

        if "text/html" in content_type:
            return None

        return response.content

    except Exception:
        return None


# =========================================================
# 대표이미지용 Base64
# =========================================================
@st.cache_data(ttl=300)
def load_image_base64(url):
    image_bytes = load_image_bytes(url)

    if not image_bytes:
        return ""

    encoded = base64.b64encode(
        image_bytes
    ).decode("utf-8")

    return (
        f"data:image/png;"
        f"base64,{encoded}"
    )


# =========================================================
# 구글 시트 읽기
# =========================================================
@st.cache_data(ttl=60)
def load_character_data():
    sheet_id = get_sheet_id(SHEET_URL)

    if not sheet_id:
        raise ValueError(
            "구글 시트 주소를 확인해주세요."
        )

    csv_url = (
        f"https://docs.google.com/"
        f"spreadsheets/d/{sheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={quote(SHEET_NAME)}"
    )

    df = pd.read_csv(csv_url)

    df = df.dropna(how="all")

    return df


# =========================================================
# 값 정리
# =========================================================
def clean(value):
    if pd.isna(value):
        return ""

    return str(value).strip()


def esc(value):
    return html.escape(
        clean(value)
    )


# =========================================================
# 숫자 파싱
# =========================================================
def parse_number(value):
    try:
        text = str(value).strip()
        text = text.replace(",", "")

        return float(text)

    except Exception:
        return None


# =========================================================
# 전투력 표시
#
# 267,349,090 → 2억 6천
# 186,507,765 → 1억 8천
# =========================================================
def format_combat_power(value):
    number = parse_number(value)

    if number is None:
        return clean(value)

    number = int(number)

    if number >= 100_000_000:
        eok = number // 100_000_000
        remainder = number % 100_000_000
        cheonman = remainder // 10_000_000

        if cheonman > 0:
            return f"{eok}억 {cheonman}천"

        return f"{eok}억"

    if number >= 10_000_000:
        cheonman = number // 10_000_000
        remainder = number % 10_000_000
        baekman = remainder // 1_000_000

        if baekman > 0:
            return f"{cheonman}천 {baekman}백만"

        return f"{cheonman}천만"

    if number >= 1_000_000:
        baekman = number // 1_000_000
        remainder = number % 1_000_000
        sibman = remainder // 100_000

        if sibman > 0:
            return f"{baekman}백 {sibman}십만"

        return f"{baekman}백만"

    return f"{number:,}"


# =========================================================
# 헥사환산 표시
#
# 74,983 → 7.5만
# =========================================================
def format_hexa(value):
    number = parse_number(value)

    if number is None:
        return clean(value)

    if number >= 10_000:
        return f"{number / 10_000:.1f}만"

    return f"{int(number):,}"


# =========================================================
# 환산주스탯 URL
# =========================================================
def get_stat_url(row):
    candidates = [
        "환산주스탯URL",
        "환산주스탯",
    ]

    for col in candidates:
        if col in row.index:
            value = clean(
                row.get(col, "")
            )

            if value.startswith("http"):
                return value

    return ""


# =========================================================
# 순위 배지
# =========================================================
def rank_badge(rank):
    try:
        rank_num = int(float(rank))
    except Exception:
        return ""

    if rank_num == 1:
        css = "rank-gold"
        icon = "♛"

    elif rank_num == 2:
        css = "rank-silver"
        icon = "♛"

    elif rank_num == 3:
        css = "rank-bronze"
        icon = "♛"

    else:
        css = "rank-normal"
        icon = "♟"

    return (
        f'<div class="rank-badge {css}">'
        f'{icon}&nbsp; {rank_num}위'
        f'</div>'
    )


# =========================================================
# 메인 CSS
# =========================================================
st.markdown(
    """
<style>

.stApp {
    background:
        radial-gradient(
            circle at top,
            #162032 0%,
            #0c111a 42%,
            #080c13 100%
        );
}

.block-container {
    max-width: 1600px;
    padding-top: 4rem;
    padding-bottom: 3rem;
}


/* HEADER */

.site-header {
    display: flex;
    align-items: center;
    gap: 18px;
    margin-bottom: 30px;
}

.site-logo {
    width: 72px;
    height: 72px;
    object-fit: contain;
}

.site-title {
    font-size: 2.4rem;
    font-weight: 900;
    letter-spacing: -1.5px;
    line-height: 1.25;
    color: #f4f7ff;
}


/* CARD */

.character-card {
    background:
        linear-gradient(
            145deg,
            rgba(20, 29, 43, 0.96),
            rgba(10, 16, 26, 0.98)
        );

    border:
        1px solid rgba(132, 161, 204, 0.28);

    border-radius: 18px;

    padding: 18px;

    min-height: 270px;

    box-shadow:
        0 12px 28px
        rgba(0, 0, 0, 0.18);
}


/* RANK */

.card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    min-height: 42px;
}

.rank-badge {
    display: inline-flex;
    align-items: center;
    padding: 5px 11px;
    border-radius: 9px;
    font-size: 0.93rem;
    font-weight: 800;
}

.rank-gold {
    color: #ffd955;
    background: rgba(130, 92, 0, 0.28);
    border: 1px solid rgba(255, 206, 55, 0.6);
}

.rank-silver {
    color: #dfe7f7;
    background: rgba(120, 135, 160, 0.20);
    border: 1px solid rgba(170, 185, 210, 0.35);
}

.rank-bronze {
    color: #ffb487;
    background: rgba(140, 76, 48, 0.24);
    border: 1px solid rgba(210, 130, 90, 0.45);
}

.rank-normal {
    color: #c9d5e9;
    background: rgba(80, 98, 125, 0.20);
    border: 1px solid rgba(140, 160, 190, 0.35);
}


/* MAIN */

.card-main {
    display: grid;
    grid-template-columns:
        125px minmax(0, 1fr);

    gap: 18px;

    align-items: center;

    margin-top: 6px;
}

.character-image-box {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 150px;
}

.character-image {
    max-width: 125px;
    max-height: 145px;
    object-fit: contain;

    filter:
        drop-shadow(
            0 6px 8px
            rgba(0, 0, 0, 0.45)
        );
}

.character-placeholder {
    width: 110px;
    height: 110px;

    border:
        1px dashed
        rgba(180, 190, 210, 0.35);

    border-radius: 14px;

    display: flex;
    align-items: center;
    justify-content: center;

    color: #8996aa;
    font-size: 0.8rem;
}


/* TEXT */

.nickname {
    color: #f7f9ff;
    font-size: 1.45rem;
    font-weight: 900;
    margin-bottom: 2px;
}

.realname {
    color: #adb9cd;
    font-size: 0.88rem;
    margin-bottom: 10px;
}


/* JOB */

.job-level-row {
    display: flex;
    align-items: center;
    justify-content: space-between;

    gap: 8px;

    margin-bottom: 13px;
}

.job-chip {
    display: inline-block;

    padding: 5px 9px;

    border-radius: 8px;

    background:
        rgba(73, 113, 162, 0.20);

    border:
        1px solid
        rgba(103, 147, 200, 0.25);

    color: #e7edf8;

    font-size: 0.87rem;

    font-weight: 700;
}

.level {
    color: #c9d2e1;
    font-size: 0.9rem;
    font-weight: 700;
}


/* STATS */

.stats-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
}

.stat-box:first-child {
    border-right:
        1px solid
        rgba(130, 150, 180, 0.18);
}

.stat-label {
    color: #8f9cb0;
    font-size: 0.77rem;
    margin-bottom: 2px;
}

.stat-value {
    color: #f3f6fd;
    font-size: 1.12rem;
    font-weight: 800;
}


/* TARGET */

.target-boss {
    margin-top: 15px;
    color: #e7edf8;
    font-size: 0.89rem;
    font-weight: 650;
}


/* EXPANDER */

div[data-testid="stExpander"] {
    border-radius: 10px;
    border:
        1px solid
        rgba(150, 107, 255, 0.55);

    background:
        rgba(63, 43, 110, 0.18);

    margin-top: 8px;
}

div[data-testid="stExpander"] summary {
    font-weight: 800;
}


/* 환산주스탯 버튼 */

div.stLinkButton > a {
    border-radius: 9px !important;

    background:
        linear-gradient(
            135deg,
            rgba(30, 90, 155, 0.72),
            rgba(23, 66, 125, 0.75)
        ) !important;

    border:
        1px solid
        rgba(65, 163, 255, 0.80) !important;

    color: #e7f5ff !important;

    font-weight: 800 !important;
}


/* 모바일 */

@media (max-width: 900px) {

    .card-main {
        grid-template-columns:
            105px minmax(0, 1fr);
    }

    .character-image {
        max-width: 105px;
        max-height: 125px;
    }

    .nickname {
        font-size: 1.25rem;
    }
}

</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# HEADER
# =========================================================
logo_path = "logo.png"

logo_html = ""

if os.path.exists(logo_path):
    with open(
        logo_path,
        "rb"
    ) as image_file:

        encoded = base64.b64encode(
            image_file.read()
        ).decode("utf-8")

    logo_html = (
        f'<img '
        f'class="site-logo" '
        f'src="data:image/png;'
        f'base64,{encoded}">'
    )


st.markdown(
    f"""
<div class="site-header">
{logo_html}
<div class="site-title">해피하우스 캐릭터 목록</div>
</div>
""",
    unsafe_allow_html=True,
)


# =========================================================
# DATA
# =========================================================
try:
    df = load_character_data()

except Exception as e:
    st.error(
        "구글 시트 데이터를 불러오지 못했습니다."
    )

    st.code(str(e))
    st.stop()


if df.empty:
    st.warning(
        "등록된 캐릭터가 없습니다."
    )

    st.stop()


# =========================================================
# 순위 정렬
# =========================================================
if "순위" in df.columns:

    df["순위정렬"] = pd.to_numeric(
        df["순위"],
        errors="coerce"
    )

    df = df.sort_values(
        by="순위정렬",
        ascending=True,
        na_position="last"
    )


# =========================================================
# 캐릭터 정보 HTML
# =========================================================
def build_character_card(row):

    rank = clean(
        row.get("순위", "")
    )

    nickname = esc(
        row.get("닉네임", "")
    )

    name = esc(
        row.get("이름", "")
    )

    job = esc(
        row.get("직업", "")
    )

    level = esc(
        row.get("레벨", "")
    )

    combat_power = clean(
        row.get("전투력", "")
    )

    hexa = clean(
        row.get("헥사환산", "")
    )

    target_boss = esc(
        row.get("목표보스", "")
    )

    image_url = clean(
        row.get(
            "대표이미지URL원본",
            ""
        )
    )

    image_data = load_image_base64(
        image_url
    )

    if image_data:
        image_html = (
            f'<img '
            f'class="character-image" '
            f'src="{image_data}">'
        )

    else:
        image_html = (
            '<div '
            'class="character-placeholder">'
            '이미지 없음'
            '</div>'
        )

    if not target_boss:
        target_boss = "미정"

    combat_text = format_combat_power(
        combat_power
    )

    hexa_text = format_hexa(
        hexa
    )

    return f"""
<div class="character-card">

<div class="card-top">
{rank_badge(rank)}
</div>

<div class="card-main">

<div class="character-image-box">
{image_html}
</div>

<div>

<div class="nickname">
{nickname}
</div>

<div class="realname">
{name}
</div>

<div class="job-level-row">

<span class="job-chip">
{job}
</span>

<span class="level">
Lv. {level}
</span>

</div>

<div class="stats-row">

<div class="stat-box">

<div class="stat-label">
전투력
</div>

<div class="stat-value">
{combat_text}
</div>

</div>

<div class="stat-box">

<div class="stat-label">
헥사환산
</div>

<div class="stat-value">
{hexa_text}
</div>

</div>

</div>

<div class="target-boss">
🎯 목표 보스:
<b>{target_boss}</b>
</div>

</div>
</div>

</div>
"""


# =========================================================
# 3열 출력
# =========================================================
CARDS_PER_ROW = 3

for start in range(
    0,
    len(df),
    CARDS_PER_ROW
):

    cols = st.columns(
        CARDS_PER_ROW,
        gap="medium"
    )

    rows = df.iloc[
        start:
        start + CARDS_PER_ROW
    ]

    for col, (_, row) in zip(
        cols,
        rows.iterrows()
    ):

        with col:

            # -----------------------------------------
            # 기본 캐릭터 카드
            # -----------------------------------------
            st.markdown(
                build_character_card(row),
                unsafe_allow_html=True
            )


            # -----------------------------------------
            # 보스배율 캡처
            # 사이트 안에서 펼쳐보기
            # -----------------------------------------
            boss_url = clean(
                row.get(
                    "보스배율캡처URL",
                    ""
                )
            )

            if boss_url:

                with st.expander(
                    "📊 보스배율 보기",
                    expanded=False
                ):

                    boss_image = load_image_bytes(
                        boss_url
                    )

                    if boss_image:

                        st.image(
                            BytesIO(boss_image),
                            use_container_width=True
                        )

                    else:

                        st.warning(
                            "보스배율 이미지를 불러오지 못했습니다."
                        )

            else:

                st.caption(
                    "보스배율 캡처 없음"
                )


            # -----------------------------------------
            # 환산주스탯
            # 상세사이트만 외부 이동
            # -----------------------------------------
            stat_url = get_stat_url(
                row
            )

            if stat_url:

                st.link_button(
                    "🔎 환산주스탯 보기",
                    stat_url,
                    use_container_width=True
                )

            else:

                st.button(
                    "환산주스탯 링크 없음",
                    disabled=True,
                    use_container_width=True,
                    key=(
                        "nostat_"
                        + clean(
                            row.get(
                                "닉네임",
                                ""
                            )
                        )
                    )
                )

            # 카드 사이 간격
            st.write("")
