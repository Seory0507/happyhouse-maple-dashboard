import os
import re
import base64
import html
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st
import gspread

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from google.oauth2.service_account import Credentials


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
# 보스 / 난이도
# 네가 순서를 바꿨다면 이 부분 순서만 원하는 대로 바꿔도 됨
# =========================================================
BOSS_DIFFICULTIES = {
    "스우": ["노멀", "하드", "익스트림"],
    "데미안": ["노멀", "하드"],
    "가디언 엔젤 슬라임": ["노멀", "카오스"],
    "루시드": ["이지", "노멀", "하드"],
    "윌": ["이지", "노멀", "하드"],
    "더스크": ["노멀", "카오스"],
    "진 힐라": ["노멀", "하드"],
    "듄켈": ["노멀", "하드"],
    "검은 마법사": ["하드", "익스트림"],
    "선택받은 세렌": ["노멀", "하드", "익스트림"],
    "감시자 칼로스": ["이지", "노멀", "카오스", "익스트림"],
    "최초의 대적자": ["이지", "노멀", "하드", "익스트림"],
    "카링": ["이지", "노멀", "하드", "익스트림"],
    "벨로나": ["이지", "노멀", "하드"],
    "림보": ["노멀", "하드"],
    "발드릭스": ["노멀", "하드"],
    "찬란한 흉성": ["노멀", "하드"],
    "유피테르": ["노멀", "하드"],
}


# =========================================================
# 설정값
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
ADMIN_PASSWORD = get_config("ADMIN_PASSWORD")
BOSS_HOPE_SHEET_NAME = "보스희망"
SPEC_REQUEST_SHEET_NAME = "스펙변경요청"
SPEC_REQUEST_HEADERS = ["닉네임", "요청일시", "확인여부", "확인일시"]


# =========================================================
# 공통 유틸
# =========================================================
def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def esc(value):
    return html.escape(clean(value))


def parse_number(value):
    try:
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def format_combat_power(value):
    number = parse_number(value)
    if number is None:
        return clean(value)

    number = int(number)

    if number >= 100_000_000:
        eok = number // 100_000_000
        remainder = number % 100_000_000
        cheonman = remainder // 10_000_000
        if cheonman:
            return f"{eok}억 {cheonman}천"
        return f"{eok}억"

    if number >= 10_000_000:
        cheonman = number // 10_000_000
        remainder = number % 10_000_000
        baekman = remainder // 1_000_000
        if baekman:
            return f"{cheonman}천 {baekman}백만"
        return f"{cheonman}천만"

    if number >= 1_000_000:
        baekman = number // 1_000_000
        return f"{baekman}백만"

    return f"{number:,}"


def format_hexa(value):
    number = parse_number(value)
    if number is None:
        return clean(value)

    if number >= 10_000:
        return f"{number / 10_000:.1f}만"

    return f"{int(number):,}"


# =========================================================
# 로컬 이미지
# =========================================================
@st.cache_data
def local_image_base64(path):
    if not os.path.exists(path):
        return ""

    try:
        with open(path, "rb") as f:
            data = f.read()

        ext = os.path.splitext(path)[1].lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(ext, "image/png")

        encoded = base64.b64encode(data).decode("utf-8")
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return ""


def get_character_local_image_path(nickname):
    nickname = str(nickname).strip()
    if not nickname:
        return ""

    for ext in [".png", ".webp", ".jpg", ".jpeg"]:
        path = os.path.join("assets", "characters", nickname + ext)
        if os.path.exists(path):
            return path

    return ""


def get_character_local_image(nickname):
    path = get_character_local_image_path(nickname)
    if path:
        return local_image_base64(path)
    return ""


# =========================================================
# 비밀번호
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
            circle at 50% -10%,
            #1d2c44 0%,
            #101927 42%,
            #080d15 100%
        );
}
.block-container {
    max-width: 520px;
    padding-top: 10rem;
}
.login-title {
    text-align: center;
    color: #f5f8ff;
    font-size: 2rem;
    font-weight: 900;
    margin-bottom: 22px;
}
</style>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="login-title">
🍁 해피하우스 캐릭터 목록
</div>
""",
        unsafe_allow_html=True,
    )

    password = st.text_input(
        "비밀번호",
        type="password",
        placeholder="비밀번호를 입력하세요",
        label_visibility="collapsed",
    )

    if st.button("입장", use_container_width=True):
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
# Google Sheet
# =========================================================
def get_sheet_id(sheet_url):
    if not sheet_url:
        return None

    try:
        return sheet_url.split("/d/")[1].split("/")[0]
    except Exception:
        return None


@st.cache_resource
def get_gspread_client():
    try:
        service_account_info = dict(st.secrets["gcp_service_account"])
    except Exception as e:
        raise RuntimeError(
            "Streamlit Secrets의 [gcp_service_account] 설정을 확인해주세요."
        ) from e

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes,
    )

    return gspread.authorize(credentials)


@st.cache_resource
def get_spreadsheet():
    sheet_id = get_sheet_id(SHEET_URL)
    if not sheet_id:
        raise RuntimeError("SHEET_URL을 확인해주세요.")

    client = get_gspread_client()
    return client.open_by_key(sheet_id)


def get_boss_hope_worksheet():
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(BOSS_HOPE_SHEET_NAME)


def get_spec_request_worksheet():
    spreadsheet = get_spreadsheet()

    try:
        worksheet = spreadsheet.worksheet(SPEC_REQUEST_SHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=SPEC_REQUEST_SHEET_NAME,
            rows=200,
            cols=len(SPEC_REQUEST_HEADERS),
        )
        worksheet.append_row(SPEC_REQUEST_HEADERS)

    header = worksheet.row_values(1)
    if header != SPEC_REQUEST_HEADERS:
        worksheet.update(
            range_name=f"A1:D1",
            values=[SPEC_REQUEST_HEADERS],
        )

    return worksheet


def now_kst_text():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")


def is_spec_request_pending(value):
    text = clean(value).lower()
    return text not in {"확인완료", "완료", "확인", "y", "yes", "true", "1"}


# =========================================================
# Google Drive 이미지
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


@st.cache_data(ttl=21600)
def load_image_bytes(url):
    if not url:
        return None

    file_id = get_drive_file_id(url)

    try:
        if file_id:
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        else:
            download_url = url

        response = requests.get(
            download_url,
            timeout=20,
            allow_redirects=True,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            return None

        return response.content

    except Exception:
        return None


@st.cache_data(ttl=21600)
def load_image_base64(url):
    image_bytes = load_image_bytes(url)
    if not image_bytes:
        return ""

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


# =========================================================
# 데이터 읽기
# =========================================================
@st.cache_data(ttl=300)
def load_character_data():
    sheet_id = get_sheet_id(SHEET_URL)
    if not sheet_id:
        raise ValueError("구글 시트 주소를 확인해주세요.")

    csv_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={quote(SHEET_NAME)}"
    )

    df = pd.read_csv(csv_url)
    return df.dropna(how="all")


@st.cache_data(ttl=60)
def load_boss_hope_data():
    worksheet = get_boss_hope_worksheet()
    records = worksheet.get_all_records()

    if not records:
        return pd.DataFrame(columns=["닉네임", "보스", "난이도", "인원"])

    df = pd.DataFrame(records)

    required_columns = ["닉네임", "보스", "난이도", "인원"]
    for col in required_columns:
        if col not in df.columns:
            df[col] = ""

    return df[required_columns]


@st.cache_data(ttl=20)
def load_spec_request_data():
    worksheet = get_spec_request_worksheet()
    records = worksheet.get_all_records()

    if not records:
        return pd.DataFrame(columns=SPEC_REQUEST_HEADERS)

    request_df = pd.DataFrame(records)
    for col in SPEC_REQUEST_HEADERS:
        if col not in request_df.columns:
            request_df[col] = ""

    return request_df[SPEC_REQUEST_HEADERS]


def request_spec_change(nickname):
    nickname = clean(nickname)
    if not nickname:
        return False

    worksheet = get_spec_request_worksheet()
    records = worksheet.get_all_records()

    for record in records:
        if clean(record.get("닉네임", "")) == nickname and is_spec_request_pending(
            record.get("확인여부", "")
        ):
            return False

    worksheet.append_row(
        [nickname, now_kst_text(), "미확인", ""],
        value_input_option="USER_ENTERED",
    )
    load_spec_request_data.clear()
    return True


def confirm_spec_change(nickname):
    nickname = clean(nickname)
    if not nickname:
        return 0

    worksheet = get_spec_request_worksheet()
    records = worksheet.get_all_records()
    updated = 0
    confirmed_at = now_kst_text()

    for row_number, record in enumerate(records, start=2):
        if clean(record.get("닉네임", "")) != nickname:
            continue
        if not is_spec_request_pending(record.get("확인여부", "")):
            continue

        worksheet.update_cell(row_number, 3, "확인완료")
        worksheet.update_cell(row_number, 4, confirmed_at)
        updated += 1

    if updated:
        load_spec_request_data.clear()

    return updated



# =========================================================
# 보스희망 저장
# =========================================================
def save_boss_hopes(nickname, hopes):
    worksheet = get_boss_hope_worksheet()

    pattern = re.compile(f"^{re.escape(nickname)}$")
    matches = worksheet.findall(pattern, in_column=1)

    rows_to_delete = sorted(
        [cell.row for cell in matches if cell.row > 1],
        reverse=True,
    )

    for row_number in rows_to_delete:
        worksheet.delete_rows(row_number)

    if hopes:
        rows = []
        for hope in hopes:
            rows.append([
                nickname,
                hope["보스"],
                hope["난이도"],
                int(hope["인원"]),
            ])

        worksheet.append_rows(
            rows,
            value_input_option="USER_ENTERED",
        )

    load_boss_hope_data.clear()


# =========================================================
# 환산 URL
# =========================================================
def get_stat_url(row):
    for col in ["환산주스탯URL", "환산주스탯"]:
        if col in row.index:
            value = clean(row.get(col, ""))
            if value.startswith("http"):
                return value
    return ""


# =========================================================
# 순위
# =========================================================
def rank_num(rank):
    try:
        return int(float(rank))
    except Exception:
        return None


def rank_html(rank):
    num = rank_num(rank)

    if num is None:
        return ""

    if num == 1:
        path = "assets/rank_gold.png"
    elif num == 2:
        path = "assets/rank_silver.png"
    elif num == 3:
        path = "assets/rank_bronze.png"
    else:
        return f'<div class="rank-normal-text">{num}위</div>'

    image = local_image_base64(path)
    if not image:
        return f'<div class="rank-normal-text">{num}위</div>'

    return (
        '<div class="rank-image-wrap">'
        f'<img src="{image}" class="rank-image">'
        f'<span>{num}위</span>'
        '</div>'
    )


def rank_card_class(rank):
    num = rank_num(rank)
    if num == 1:
        return "rank-card-gold"
    if num == 2:
        return "rank-card-silver"
    if num == 3:
        return "rank-card-bronze"
    return ""


# =========================================================
# 한글 폰트
# =========================================================
def find_korean_font(bold=False):
    font_dir = os.path.join("assets", "fonts")

    if bold:
        candidates = [
            "assets/fonts/NotoSansKR-Bold.ttf",
            "assets/fonts/NotoSansKR-Bold.otf",
            "assets/NotoSansKR-Bold.ttf",
            "C:/Windows/Fonts/malgunbd.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        ]
    else:
        candidates = [
            "assets/fonts/NotoSansKR-Regular.ttf",
            "assets/fonts/NotoSansKR-Regular.otf",
            "assets/NotoSansKR-Regular.ttf",
            "C:/Windows/Fonts/malgun.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        ]

    for path in candidates:
        if os.path.exists(path):
            return path

    if os.path.isdir(font_dir):
        font_files = [
            filename
            for filename in os.listdir(font_dir)
            if filename.lower().endswith((".ttf", ".otf", ".ttc"))
        ]

        if bold:
            for filename in font_files:
                lower_name = filename.lower()
                if "noto" in lower_name and "bold" in lower_name:
                    return os.path.join(font_dir, filename)

        for filename in font_files:
            if "noto" in filename.lower():
                return os.path.join(font_dir, filename)

        if len(font_files) == 1:
            return os.path.join(font_dir, font_files[0])

    return None


def load_party_fonts():
    regular_path = find_korean_font(bold=False)
    bold_path = find_korean_font(bold=True) or regular_path

    if regular_path:
        try:
            return (
                ImageFont.truetype(bold_path, 46),
                ImageFont.truetype(bold_path, 28),
                ImageFont.truetype(regular_path, 22),
                ImageFont.truetype(regular_path, 17),
            )
        except Exception:
            pass

    return (
        ImageFont.load_default(),
        ImageFont.load_default(),
        ImageFont.load_default(),
        ImageFont.load_default(),
    )


def load_character_card_fonts():
    regular_path = find_korean_font(bold=False)
    bold_path = find_korean_font(bold=True) or regular_path

    if regular_path:
        try:
            return {
                "rank": ImageFont.truetype(bold_path, 17),
                "nickname": ImageFont.truetype(bold_path, 31),
                "name": ImageFont.truetype(regular_path, 17),
                "chip": ImageFont.truetype(regular_path, 16),
                "level": ImageFont.truetype(bold_path, 22),
                "stat_label": ImageFont.truetype(regular_path, 15),
                "stat_value": ImageFont.truetype(bold_path, 25),
                "section": ImageFont.truetype(bold_path, 18),
                "boss": ImageFont.truetype(regular_path, 17),
            }
        except Exception:
            pass

    default = ImageFont.load_default()
    return {
        "rank": default,
        "nickname": default,
        "name": default,
        "chip": default,
        "level": default,
        "stat_label": default,
        "stat_value": default,
        "section": default,
        "boss": default,
    }


# =========================================================
# CSS
# =========================================================
st.markdown(
    """
<style>
.stApp {
    background:
        radial-gradient(
            circle at 50% -12%,
            rgba(29,49,79,.98) 0%,
            rgba(13,22,35,1) 43%,
            rgba(7,12,20,1) 100%
        );
}

.block-container {
    max-width: 1580px;
    padding-top: 3.2rem;
    padding-bottom: 4rem;
}

.main-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 16px;
}

.main-logo {
    width: 70px;
    height: 70px;
    object-fit: contain;
}

.main-title {
    color: #f8faff;
    font-size: 2.45rem;
    font-weight: 900;
    letter-spacing: -1.8px;
}

.maple-logo {
    max-width: 190px;
    max-height: 78px;
    object-fit: contain;
}

.character-card {
    position: relative;
    overflow: hidden;
    background:
        linear-gradient(
            145deg,
            rgba(20,31,47,.98),
            rgba(9,16,26,.99)
        );
    border: 1px solid rgba(126,153,192,.28);
    border-radius: 20px;
    padding: 17px 18px 18px 18px;
    min-height: 285px;
    box-shadow: 0 15px 32px rgba(0,0,0,.23);
}

.rank-card-gold {
    border-color: rgba(218,174,50,.54);
}

.rank-card-silver {
    border-color: rgba(172,187,211,.43);
}

.rank-card-bronze {
    border-color: rgba(193,116,77,.46);
}

.card-top {
    height: 36px;
}

.rank-image-wrap {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #e9eef8;
    font-size: .90rem;
    font-weight: 850;
}

.rank-image {
    width: 27px;
    height: 27px;
    object-fit: contain;
}

.rank-normal-text {
    color: #c1cede;
    font-size: .91rem;
    font-weight: 800;
    padding-top: 5px;
}

.card-main {
    display: grid;
    grid-template-columns: 128px minmax(0,1fr);
    gap: 17px;
    align-items: center;
}

.character-image-box {
    position: relative;
    height: 150px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.character-image-box::before {
    content: "";
    position: absolute;
    width: 112px;
    height: 112px;
    border-radius: 50%;
    background:
        radial-gradient(
            circle,
            rgba(95,151,222,.13),
            rgba(67,108,159,.025) 62%,
            transparent 76%
        );
}

.character-image {
    position: relative;
    z-index: 2;
    max-width: 132px;
    max-height: 148px;
    object-fit: contain;
    filter: drop-shadow(0 8px 10px rgba(0,0,0,.46));
}

.nickname {
    font-size: 1.45rem;
    color: #f9faff;
    font-weight: 900;
    letter-spacing: -.8px;
}

.realname {
    color: #94a6bf;
    font-size: .86rem;
    margin-bottom: 10px;
}

.job-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 13px;
}

.job-left-group {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 7px;
}

.job-chip {
    background: rgba(59,94,137,.25);
    border: 1px solid rgba(102,147,203,.30);
    border-radius: 8px;
    padding: 5px 9px;
    color: #eaf0fa;
    font-size: .84rem;
    font-weight: 750;
}

.level-left {
    color: #d8e2f1;
    font-size: 1.00rem;
    font-weight: 800;
    line-height: 1;
}

.right-meta {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 6px;
}

.spec-change-link {
    display: inline-block;
    text-decoration: none !important;
    padding: 4px 8px;
    border-radius: 8px;
    background: rgba(128, 91, 36, .24);
    border: 1px solid rgba(219, 164, 75, .42);
    color: #f4cf8a !important;
    font-size: .72rem;
    font-weight: 800;
}

.spec-change-link:hover {
    background: rgba(157, 108, 39, .38);
    color: #fff1cc !important;
}

.spec-change-pending {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 8px;
    background: rgba(107, 82, 36, .14);
    border: 1px solid rgba(193, 151, 72, .24);
    color: #bca97e;
    font-size: .70rem;
    font-weight: 800;
    cursor: default;
    opacity: .82;
}

.stat-chip-link {
    display: inline-block;
    text-decoration: none !important;
    padding: 4px 8px;
    border-radius: 8px;
    background: rgba(29,87,150,.35);
    border: 1px solid rgba(76,157,238,.38);
    color: #cce9ff !important;
    font-size: .72rem;
    font-weight: 800;
}

.stat-chip-link:hover {
    background: rgba(40,107,177,.55);
    color: #ffffff !important;
}

.server-chip {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 8px;
    background: rgba(75,106,148,.17);
    border: 1px solid rgba(115,151,199,.24);
    color: #b7cce6;
    font-size: .74rem;
    font-weight: 750;
}

.level {
    color: #ccd6e6;
    font-size: .95rem;
    font-weight: 800;
}

.stats-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
}

.stat-box:first-child {
    border-right: 1px solid rgba(126,149,182,.17);
}

.stat-label {
    color: #8191aa;
    font-size: .73rem;
}

.stat-value {
    color: #f6f8fe;
    font-size: 1.10rem;
    font-weight: 850;
}

.boss-hope-area {
    margin-top: 13px;
    padding-top: 10px;
    border-top: 1px solid rgba(115,139,172,.15);
}

.boss-hope-title {
    color: #9bb0ca;
    font-size: .75rem;
    font-weight: 800;
    margin-bottom: 5px;
}

.boss-hope-item {
    color: #e4ecf8;
    font-size: .84rem;
    font-weight: 700;
    line-height: 1.52;
}

.boss-hope-empty {
    color: #71849e;
    font-size: .82rem;
}

.hope-editor-title {
    color: #edf3ff;
    font-size: 1.02rem;
    font-weight: 850;
    margin-top: 10px;
    margin-bottom: 5px;
}

div[data-testid="stExpander"] {
    border-radius: 10px;
    border: 1px solid rgba(144,107,234,.53);
    background: rgba(69,47,115,.19);
    overflow: hidden;
    margin-top: 7px;
}

.party-page-title {
    font-size: 1.65rem;
    color: #f7f9ff;
    font-weight: 900;
    margin-top: 15px;
    margin-bottom: 3px;
}

.party-description {
    color: #8fa0b8;
    font-size: .86rem;
    margin-bottom: 20px;
}

.party-section-title {
    color: #edf3ff;
    font-size: 1.10rem;
    font-weight: 850;
    margin-top: 18px;
    margin-bottom: 6px;
}

.completed-boss {
    background:
        linear-gradient(
            145deg,
            rgba(24,37,56,.98),
            rgba(11,18,29,.98)
        );
    border: 1px solid rgba(90,145,205,.30);
    border-radius: 16px;
    padding: 16px 18px;
    margin-bottom: 8px;
}

.completed-boss-title {
    color: #f7f9ff;
    font-size: 1.12rem;
    font-weight: 900;
}

.completed-boss-info {
    color: #95a7bf;
    font-size: .82rem;
    margin-top: 3px;
}

.final-boss-card {
    background:
        linear-gradient(
            145deg,
            rgba(18,29,45,.99),
            rgba(8,14,23,.99)
        );
    border: 1px solid rgba(112,151,204,.34);
    border-radius: 18px;
    padding: 18px 20px;
    margin-bottom: 15px;
}

.final-boss-name {
    color: #ffffff;
    font-size: 1.25rem;
    font-weight: 900;
    margin-bottom: 10px;
}

.final-party-line {
    color: #dde8f7;
    padding: 8px 0;
    border-bottom: 1px solid rgba(105,129,162,.13);
}

.final-party-stat {
    color: #8094af;
    font-size: .78rem;
    margin-top: 3px;
}

@media (max-width: 1000px) {
    .maple-logo {
        max-width: 145px;
    }

    .card-main {
        grid-template-columns: 105px minmax(0,1fr);
    }

    .character-image {
        max-width: 108px;
        max-height: 126px;
    }
}
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# HEADER
# =========================================================
main_logo = local_image_base64("assets/logo_main.png")
maple_logo = local_image_base64("assets/logo_maplestory.png")

main_logo_html = ""
if main_logo:
    main_logo_html = f'<img class="main-logo" src="{main_logo}">'

maple_logo_html = ""
if maple_logo:
    maple_logo_html = f'<img class="maple-logo" src="{maple_logo}">'

header_html = "".join([
    '<div class="main-header">',
    '<div class="header-left">',
    main_logo_html,
    '<div class="main-title">해피하우스 캐릭터 목록</div>',
    '</div>',
    '<div>',
    maple_logo_html,
    '</div>',
    '</div>',
])

st.markdown(header_html, unsafe_allow_html=True)


# =========================================================
# DATA
# =========================================================
try:
    df = load_character_data()
except Exception as e:
    st.error("구글 시트의 캐릭터 데이터를 불러오지 못했습니다.")
    st.code(str(e))
    st.stop()

try:
    boss_hope_df = load_boss_hope_data()
except Exception as e:
    st.error("보스희망 시트를 불러오지 못했습니다.")
    st.code(str(e))
    st.stop()

try:
    spec_request_df = load_spec_request_data()
except Exception as e:
    st.error("스펙변경요청 시트를 불러오지 못했습니다.")
    st.code(str(e))
    st.stop()

if df.empty:
    st.warning("등록된 캐릭터가 없습니다.")
    st.stop()


# =========================================================
# 스펙 변경 요청 상태 / 요청 처리
# =========================================================
pending_spec_request_nicknames = set()
pending_spec_request_rows = []

for _, request_row in spec_request_df.iterrows():
    nickname = clean(request_row.get("닉네임", ""))
    if nickname and is_spec_request_pending(request_row.get("확인여부", "")):
        pending_spec_request_nicknames.add(nickname)
        pending_spec_request_rows.append(
            {
                "닉네임": nickname,
                "요청일시": clean(request_row.get("요청일시", "")),
            }
        )

try:
    spec_request_param = st.query_params.get("spec_request", "")
except Exception:
    params = st.experimental_get_query_params()
    spec_request_param = params.get("spec_request", [""])[0]

if isinstance(spec_request_param, list):
    spec_request_param = spec_request_param[0] if spec_request_param else ""

spec_request_param = clean(spec_request_param)
valid_nicknames = set(df.get("닉네임", pd.Series(dtype=str)).fillna("").astype(str).str.strip())

if spec_request_param:
    if spec_request_param in valid_nicknames:
        created = request_spec_change(spec_request_param)
        if created:
            st.session_state["spec_request_message"] = (
                f"{spec_request_param}의 스펙 변경 요청을 등록했습니다."
            )
        else:
            st.session_state["spec_request_message"] = (
                f"{spec_request_param}은(는) 이미 변경 확인 대기 중입니다."
            )

    try:
        st.query_params.clear()
    except Exception:
        st.experimental_set_query_params()
    st.rerun()


# =========================================================
# SORT / ID
# =========================================================
if "순위" in df.columns:
    df["순위정렬"] = pd.to_numeric(df["순위"], errors="coerce")
    df = df.sort_values("순위정렬", ascending=True, na_position="last")

df = df.reset_index(drop=True)
df["_캐릭터ID"] = df.index.astype(int)


# =========================================================
# CHARACTER LOOKUP
# =========================================================
character_lookup = {}

for _, row in df.iterrows():
    cid = int(row["_캐릭터ID"])
    character_lookup[cid] = {
        "id": cid,
        "nickname": clean(row.get("닉네임", "")),
        "name": clean(row.get("이름", "")),
        "job": clean(row.get("직업", "")),
        "server": clean(row.get("서버", "")),
        "level": clean(row.get("레벨", "")),
        "combat": parse_number(row.get("전투력", "")) or 0,
        "hexa": parse_number(row.get("헥사환산", "")) or 0,
    }

all_character_ids = list(character_lookup.keys())


# =========================================================
# BOSS HOPE LOOKUP
# =========================================================
boss_hope_lookup = {}

for _, hope_row in boss_hope_df.iterrows():
    nickname = clean(hope_row.get("닉네임", ""))
    boss = clean(hope_row.get("보스", ""))
    difficulty = clean(hope_row.get("난이도", ""))
    people = parse_number(hope_row.get("인원", ""))

    if not nickname:
        continue

    if nickname not in boss_hope_lookup:
        boss_hope_lookup[nickname] = []

    boss_hope_lookup[nickname].append(
        {
            "보스": boss,
            "난이도": difficulty,
            "인원": int(people) if people is not None else 1,
        }
    )


# =========================================================
# BOSS HOPE HTML
# =========================================================
def boss_hope_html(nickname):
    hopes = boss_hope_lookup.get(nickname, [])

    if not hopes:
        return "".join([
            '<div class="boss-hope-area">',
            '<div class="boss-hope-title">🎯 가고 싶은 보스</div>',
            '<div class="boss-hope-empty">등록된 보스가 없습니다.</div>',
            '</div>',
        ])

    lines = []
    for hope in hopes:
        boss = html.escape(str(hope["보스"]))
        difficulty = html.escape(str(hope["난이도"]))
        people = int(hope["인원"])

        lines.append(
            "".join([
                '<div class="boss-hope-item">',
                f'{difficulty} {boss} · {people}인',
                '</div>',
            ])
        )

    return "".join([
        '<div class="boss-hope-area">',
        '<div class="boss-hope-title">🎯 가고 싶은 보스</div>',
        "".join(lines),
        '</div>',
    ])


# =========================================================
# CHARACTER CARD HTML
# =========================================================
def build_card(row):
    rank = clean(row.get("순위", ""))
    nickname_raw = clean(row.get("닉네임", ""))
    nickname = html.escape(nickname_raw)
    name = esc(row.get("이름", ""))
    job = esc(row.get("직업", ""))
    server = esc(row.get("서버", ""))
    level = esc(row.get("레벨", ""))

    combat_text = format_combat_power(row.get("전투력", ""))
    hexa_text = format_hexa(row.get("헥사환산", ""))

    image = get_character_local_image(nickname_raw)

    if not image:
        image_url = clean(row.get("대표이미지URL원본", ""))
        image = load_image_base64(image_url)

    image_html = ""
    if image:
        image_html = f'<img class="character-image" src="{image}">'

    spec_change_html = ""
    if nickname_raw in pending_spec_request_nicknames:
        spec_change_html = (
            '<span class="spec-change-pending" title="관리자 확인 대기 중">'
            '⏳ 변경 확인 필요'
            '</span>'
        )
    else:
        spec_request_url = f"?spec_request={quote(nickname_raw)}"
        spec_change_html = (
            '<a class="spec-change-link" '
            f'href="{spec_request_url}" target="_self" '
            'title="스펙이 바뀌었으면 눌러주세요">'
            '🔄 스펙변경'
            '</a>'
        )

    stat_url = get_stat_url(row)
    stat_link_html = ""

    if stat_url:
        safe_url = html.escape(stat_url, quote=True)
        stat_link_html = "".join([
            '<a class="stat-chip-link" ',
            f'href="{safe_url}" ',
            'target="_blank">',
            '🔎 환산주스탯',
            '</a>',
        ])

    server_html = ""
    if server:
        server_html = f'<span class="server-chip">{server}</span>'

    hope_html = boss_hope_html(nickname_raw)

    return "".join([
        f'<div class="character-card {rank_card_class(rank)}">',

        '<div class="card-top">',
        rank_html(rank),
        '</div>',

        '<div class="card-main">',

        '<div class="character-image-box">',
        image_html,
        '</div>',

        '<div>',

        f'<div class="nickname">{nickname}</div>',
        f'<div class="realname">{name}</div>',

        '<div class="job-row">',

        '<div class="job-left-group">',
        f'<span class="job-chip">{job}</span>',
        f'<span class="level-left">Lv. {level}</span>',
        '</div>',

        '<div class="right-meta">',
        spec_change_html,
        stat_link_html,
        server_html,
        '</div>',

        '</div>',

        '<div class="stats-row">',

        '<div class="stat-box">',
        '<div class="stat-label">전투력</div>',
        f'<div class="stat-value">{combat_text}</div>',
        '</div>',

        '<div class="stat-box">',
        '<div class="stat-label">헥사환산</div>',
        f'<div class="stat-value">{hexa_text}</div>',
        '</div>',

        '</div>',

        hope_html,

        '</div>',

        '</div>',

        '</div>',
    ])


# =========================================================
# 저장용 캐릭터 이미지 관련
# =========================================================
def open_character_image_for_render(row):
    nickname = clean(row.get("닉네임", ""))
    local_path = get_character_local_image_path(nickname)

    try:
        if local_path:
            return Image.open(local_path).convert("RGBA")

        image_url = clean(row.get("대표이미지URL원본", ""))
        image_bytes = load_image_bytes(image_url)
        if image_bytes:
            return Image.open(BytesIO(image_bytes)).convert("RGBA")

    except Exception:
        return None

    return None


def resize_image_keep_ratio(image, max_w, max_h):
    if image is None:
        return None

    w, h = image.size
    if w == 0 or h == 0:
        return image

    scale = min(max_w / w, max_h / h)
    new_size = (
        max(1, int(w * scale)),
        max(1, int(h * scale)),
    )

    return image.resize(new_size, Image.LANCZOS)


def paste_center(base, overlay, center_x, center_y):
    if overlay is None:
        return

    x = int(center_x - overlay.width / 2)
    y = int(center_y - overlay.height / 2)

    base.alpha_composite(overlay, (x, y))


def load_rank_icon_for_png(rank_value):
    path = ""

    if rank_value == 1:
        path = "assets/rank_gold.png"
    elif rank_value == 2:
        path = "assets/rank_silver.png"
    elif rank_value == 3:
        path = "assets/rank_bronze.png"

    if not path or not os.path.exists(path):
        return None

    try:
        image = Image.open(path).convert("RGBA")
        return resize_image_keep_ratio(image, 34, 34)
    except Exception:
        return None


# =========================================================
# 저장용 캐릭터 카드 PNG
# =========================================================
def build_character_card_image(row):
    fonts = load_character_card_fonts()

    nickname = clean(row.get("닉네임", ""))
    realname = clean(row.get("이름", ""))
    job = clean(row.get("직업", ""))
    server = clean(row.get("서버", ""))
    level = clean(row.get("레벨", ""))
    rank = clean(row.get("순위", ""))

    combat_text = format_combat_power(row.get("전투력", ""))
    hexa_text = format_hexa(row.get("헥사환산", ""))

    hopes = boss_hope_lookup.get(nickname, [])

    width = 860
    boss_count = max(1, len(hopes))
    height = 505 + boss_count * 34

    image = Image.new("RGBA", (width, height), (7, 13, 22, 255))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        [18, 18, width - 18, height - 18],
        radius=25,
        fill=(18, 30, 47, 255),
        outline=(91, 143, 205, 210),
        width=2,
    )

    rank_value = rank_num(rank)
    rank_icon = load_rank_icon_for_png(rank_value)

    if rank_icon is not None:
        image.alpha_composite(rank_icon, (42, 37))
        draw.text(
            (81, 43),
            f"{rank_value}위",
            font=fonts["rank"],
            fill=(225, 233, 245, 255),
        )
    elif rank_value is not None:
        draw.text(
            (42, 43),
            f"{rank_value}위",
            font=fonts["rank"],
            fill=(225, 233, 245, 255),
        )

    character_center_x = 155
    character_center_y = 205

    draw.ellipse(
        [76, 126, 234, 284],
        fill=(50, 82, 122, 130),
    )

    char_img = open_character_image_for_render(row)
    if char_img is not None:
        char_img = resize_image_keep_ratio(char_img, 205, 225)
        paste_center(image, char_img, character_center_x, character_center_y)

    info_x = 285

    draw.text(
        (info_x, 83),
        nickname,
        font=fonts["nickname"],
        fill=(248, 250, 255, 255),
    )

    draw.text(
        (info_x + 2, 128),
        realname,
        font=fonts["name"],
        fill=(145, 164, 190, 255),
    )

    chip_top = 169

    job_bbox = draw.textbbox((0, 0), job, font=fonts["chip"])
    job_width = job_bbox[2] - job_bbox[0] + 26

    draw.rounded_rectangle(
        [info_x, chip_top, info_x + job_width, chip_top + 34],
        radius=9,
        fill=(44, 67, 97, 210),
        outline=(92, 133, 185, 150),
        width=1,
    )

    draw.text(
        (info_x + 13, chip_top + 6),
        job,
        font=fonts["chip"],
        fill=(231, 239, 250, 255),
    )

    # 레벨을 직업 아래 왼쪽으로 이동
    draw.text(
        (info_x, chip_top + 46),
        f"Lv. {level}",
        font=fonts["level"],
        fill=(216, 225, 239, 255),
    )

    meta_x = 620

    if server:
        server_bbox = draw.textbbox((0, 0), server, font=fonts["chip"])
        server_width = server_bbox[2] - server_bbox[0] + 24

        draw.rounded_rectangle(
            [meta_x, chip_top, meta_x + server_width, chip_top + 33],
            radius=9,
            fill=(38, 55, 79, 205),
            outline=(91, 127, 173, 120),
            width=1,
        )

        draw.text(
            (meta_x + 12, chip_top + 6),
            server,
            font=fonts["chip"],
            fill=(188, 211, 239, 255),
        )

    stat_top = 278

    draw.line(
        (info_x, stat_top, 805, stat_top),
        fill=(76, 102, 136, 110),
        width=1,
    )

    stat_left_x = info_x
    stat_right_x = 550

    draw.text(
        (stat_left_x, stat_top + 20),
        "전투력",
        font=fonts["stat_label"],
        fill=(128, 147, 173, 255),
    )

    draw.text(
        (stat_left_x, stat_top + 48),
        combat_text,
        font=fonts["stat_value"],
        fill=(247, 249, 255, 255),
    )

    draw.line(
        (520, stat_top + 15, 520, stat_top + 83),
        fill=(76, 102, 136, 85),
        width=1,
    )

    draw.text(
        (stat_right_x, stat_top + 20),
        "헥사환산",
        font=fonts["stat_label"],
        fill=(128, 147, 173, 255),
    )

    draw.text(
        (stat_right_x, stat_top + 48),
        hexa_text,
        font=fonts["stat_value"],
        fill=(247, 249, 255, 255),
    )

    boss_section_y = 365

    draw.line(
        (42, boss_section_y, width - 42, boss_section_y),
        fill=(76, 102, 136, 100),
        width=1,
    )

    draw.text(
        (46, boss_section_y + 20),
        "가고 싶은 보스",
        font=fonts["section"],
        fill=(164, 187, 216, 255),
    )

    boss_y = boss_section_y + 61

    if hopes:
        for hope in hopes:
            difficulty = clean(hope.get("난이도", ""))
            boss = clean(hope.get("보스", ""))
            people = int(hope.get("인원", 1))

            line = f"{difficulty} {boss} · {people}인"

            draw.text(
                (50, boss_y),
                line,
                font=fonts["boss"],
                fill=(229, 237, 248, 255),
            )

            boss_y += 34

    else:
        draw.text(
            (50, boss_y),
            "등록된 보스가 없습니다.",
            font=fonts["boss"],
            fill=(117, 138, 165, 255),
        )

    output = BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)

    return output.getvalue()


# =========================================================
# 보스희망 편집 상태
# =========================================================
if "editing_hope_nickname" not in st.session_state:
    st.session_state["editing_hope_nickname"] = None

if "boss_hope_saved_message" not in st.session_state:
    st.session_state["boss_hope_saved_message"] = ""


def hope_boss_key(cid, index):
    return f"hope_boss_{cid}_{index}"


def hope_diff_key(cid, index):
    return f"hope_diff_{cid}_{index}"


def hope_people_key(cid, index):
    return f"hope_people_{cid}_{index}"


def hope_count_key(cid):
    return f"hope_row_count_{cid}"


def clear_hope_editor_keys(cid):
    prefix_list = [
        f"hope_boss_{cid}_",
        f"hope_diff_{cid}_",
        f"hope_people_{cid}_",
    ]

    keys = list(st.session_state.keys())

    for key in keys:
        if any(str(key).startswith(prefix) for prefix in prefix_list):
            del st.session_state[key]

    count_key = hope_count_key(cid)
    if count_key in st.session_state:
        del st.session_state[count_key]


def initialize_hope_editor(cid, nickname):
    clear_hope_editor_keys(cid)

    existing = boss_hope_lookup.get(nickname, [])

    if not existing:
        default_boss = list(BOSS_DIFFICULTIES.keys())[0]
        existing = [
            {
                "보스": default_boss,
                "난이도": BOSS_DIFFICULTIES[default_boss][0],
                "인원": 2,
            }
        ]

    st.session_state[hope_count_key(cid)] = len(existing)

    for index, hope in enumerate(existing):
        boss = clean(hope.get("보스", ""))
        if boss not in BOSS_DIFFICULTIES:
            boss = list(BOSS_DIFFICULTIES.keys())[0]

        difficulty = clean(hope.get("난이도", ""))
        if difficulty not in BOSS_DIFFICULTIES[boss]:
            difficulty = BOSS_DIFFICULTIES[boss][0]

        people = int(hope.get("인원", 2))
        people = max(1, min(people, 6))

        st.session_state[hope_boss_key(cid, index)] = boss
        st.session_state[hope_diff_key(cid, index)] = difficulty
        st.session_state[hope_people_key(cid, index)] = people

    st.session_state["editing_hope_nickname"] = nickname


# =========================================================
# 삭제 후 편집기 재구성
# =========================================================
if "pending_hope_rebuild" in st.session_state:
    rebuild = st.session_state["pending_hope_rebuild"]

    cid = rebuild["cid"]
    nickname = rebuild["nickname"]
    rows = rebuild["rows"]

    clear_hope_editor_keys(cid)

    if not rows:
        default_boss = list(BOSS_DIFFICULTIES.keys())[0]
        rows = [
            {
                "보스": default_boss,
                "난이도": BOSS_DIFFICULTIES[default_boss][0],
                "인원": 2,
            }
        ]

    st.session_state[hope_count_key(cid)] = len(rows)

    for index, row_data in enumerate(rows):
        st.session_state[hope_boss_key(cid, index)] = row_data["보스"]
        st.session_state[hope_diff_key(cid, index)] = row_data["난이도"]
        st.session_state[hope_people_key(cid, index)] = int(row_data["인원"])

    st.session_state["editing_hope_nickname"] = nickname
    del st.session_state["pending_hope_rebuild"]


def collect_hope_editor_rows(cid):
    count = int(st.session_state.get(hope_count_key(cid), 1))
    rows = []

    for index in range(count):
        boss = st.session_state.get(
            hope_boss_key(cid, index),
            list(BOSS_DIFFICULTIES.keys())[0],
        )

        difficulty = st.session_state.get(
            hope_diff_key(cid, index),
            BOSS_DIFFICULTIES[boss][0],
        )

        people = int(st.session_state.get(hope_people_key(cid, index), 2))

        rows.append(
            {
                "보스": boss,
                "난이도": difficulty,
                "인원": people,
            }
        )

    return rows


def render_hope_editor(cid, nickname):
    st.markdown(
        """
<div class="hope-editor-title">
🎯 가고 싶은 보스 수정
</div>
""",
        unsafe_allow_html=True,
    )

    count_key = hope_count_key(cid)

    if count_key not in st.session_state:
        initialize_hope_editor(cid, nickname)

    row_count = int(st.session_state[count_key])

    for index in range(row_count):
        boss_key = hope_boss_key(cid, index)
        diff_key = hope_diff_key(cid, index)
        people_key = hope_people_key(cid, index)

        if boss_key not in st.session_state:
            first_boss = list(BOSS_DIFFICULTIES.keys())[0]
            st.session_state[boss_key] = first_boss

        selected_boss = st.session_state[boss_key]
        difficulty_options = BOSS_DIFFICULTIES[selected_boss]

        if diff_key not in st.session_state:
            st.session_state[diff_key] = difficulty_options[0]
        elif st.session_state[diff_key] not in difficulty_options:
            st.session_state[diff_key] = difficulty_options[0]

        if people_key not in st.session_state:
            st.session_state[people_key] = 2

        c1, c2, c3, c4 = st.columns([2.2, 1.3, 1.0, .65])

        with c1:
            st.selectbox(
                "보스",
                options=list(BOSS_DIFFICULTIES.keys()),
                key=boss_key,
            )

        selected_boss = st.session_state[boss_key]
        difficulty_options = BOSS_DIFFICULTIES[selected_boss]

        if st.session_state[diff_key] not in difficulty_options:
            st.session_state[diff_key] = difficulty_options[0]

        with c2:
            st.selectbox(
                "난이도",
                options=difficulty_options,
                key=diff_key,
            )

        with c3:
            st.selectbox(
                "인원",
                options=list(range(1, 7)),
                format_func=lambda x: f"{x}인",
                key=people_key,
            )

        with c4:
            st.write("")
            st.write("")

            if st.button(
                "×",
                key=f"delete_hope_{cid}_{index}",
                help="이 보스 삭제",
                use_container_width=True,
            ):
                current_rows = collect_hope_editor_rows(cid)

                remaining_rows = [
                    row_data
                    for row_index, row_data in enumerate(current_rows)
                    if row_index != index
                ]

                st.session_state["pending_hope_rebuild"] = {
                    "cid": cid,
                    "nickname": nickname,
                    "rows": remaining_rows,
                }

                st.rerun()

    add_col, save_col, cancel_col = st.columns([1, 1, 1])

    with add_col:
        if st.button(
            "➕ 보스 추가",
            key=f"add_hope_{cid}",
            use_container_width=True,
        ):
            new_index = row_count
            first_boss = list(BOSS_DIFFICULTIES.keys())[0]

            st.session_state[count_key] = row_count + 1
            st.session_state[hope_boss_key(cid, new_index)] = first_boss
            st.session_state[hope_diff_key(cid, new_index)] = BOSS_DIFFICULTIES[first_boss][0]
            st.session_state[hope_people_key(cid, new_index)] = 2

            st.rerun()

    with save_col:
        if st.button(
            "💾 저장",
            key=f"save_hope_{cid}",
            type="primary",
            use_container_width=True,
        ):
            rows = collect_hope_editor_rows(cid)

            try:
                save_boss_hopes(nickname, rows)

                st.session_state["editing_hope_nickname"] = None
                st.session_state["boss_hope_saved_message"] = f"{nickname}의 보스희망을 저장했습니다."
                st.rerun()

            except Exception as e:
                st.error("보스희망 저장에 실패했습니다.")
                st.code(str(e))

    with cancel_col:
        if st.button(
            "취소",
            key=f"cancel_hope_{cid}",
            use_container_width=True,
        ):
            st.session_state["editing_hope_nickname"] = None
            st.rerun()


# =========================================================
# 파티 관련
# =========================================================
def character_option_text(cid):
    data = character_lookup[cid]
    return f"{data['nickname']} | {data['job']} | {data['server']} | {format_hexa(data['hexa'])}"


def get_boss_hope_candidates(boss_name, difficulty):
    exact_matches = {}
    other_matches = {}

    for cid, character in character_lookup.items():
        nickname = character["nickname"]
        hopes = boss_hope_lookup.get(nickname, [])

        for hope in hopes:
            if clean(hope.get("보스", "")) != boss_name:
                continue

            hope_data = {
                "cid": cid,
                "nickname": nickname,
                "job": character["job"],
                "server": character["server"],
                "hexa": character["hexa"],
                "difficulty": clean(hope.get("난이도", "")),
                "people": int(hope.get("인원", 1)),
            }

            if hope_data["difficulty"] == difficulty:
                exact_matches[cid] = hope_data
            else:
                other_matches[cid] = hope_data

    return list(exact_matches.values()), list(other_matches.values())


def hope_candidate_text(candidate):
    return (
        f"{candidate['nickname']} | {candidate['job']} | "
        f"헥사 {format_hexa(candidate['hexa'])} | {candidate['people']}인 희망"
    )


def other_hope_text(candidate):
    return (
        f"{candidate['nickname']} | {candidate['job']} | "
        f"{candidate['difficulty']} · {candidate['people']}인 희망 | "
        f"헥사 {format_hexa(candidate['hexa'])}"
    )


def calculate_party_stats(member_ids):
    if not member_ids:
        return 0, 0

    total_combat = sum(character_lookup[cid]["combat"] for cid in member_ids)

    valid_hexa = [
        character_lookup[cid]["hexa"]
        for cid in member_ids
        if character_lookup[cid]["hexa"] > 0
    ]

    average_hexa = sum(valid_hexa) / len(valid_hexa) if valid_hexa else 0

    return int(total_combat), average_hexa


# =========================================================
# 파티 SESSION
# =========================================================
if "completed_bosses" not in st.session_state:
    st.session_state.completed_bosses = {}

if "show_final_result" not in st.session_state:
    st.session_state.show_final_result = False


def clear_party_widget_keys():
    keys = [
        "party_boss_name",
        "party_boss_difficulty",
        "party_count",
        "party_target_boss",
    ]

    for i in range(1, 11):
        keys.append(f"party_members_{i}")

    for key in keys:
        if key in st.session_state:
            del st.session_state[key]


if st.session_state.get("pending_clear_party_editor", False):
    clear_party_widget_keys()
    del st.session_state["pending_clear_party_editor"]

if "pending_load_boss" in st.session_state:
    completed_key = st.session_state["pending_load_boss"]
    boss_data = st.session_state.completed_bosses.get(completed_key)

    clear_party_widget_keys()

    if boss_data:
        st.session_state["party_boss_name"] = boss_data["boss"]
        st.session_state["party_boss_difficulty"] = boss_data["difficulty"]
        st.session_state["party_count"] = boss_data["party_count"]

        for i, members in enumerate(boss_data["parties"], start=1):
            st.session_state[f"party_members_{i}"] = list(members)

    del st.session_state["pending_load_boss"]

if "party_boss_name" not in st.session_state:
    st.session_state["party_boss_name"] = list(BOSS_DIFFICULTIES.keys())[0]

if "party_count" not in st.session_state:
    st.session_state["party_count"] = 1


def save_current_boss():
    boss_name = st.session_state.get("party_boss_name", "")
    difficulty = st.session_state.get("party_boss_difficulty", "")

    if not boss_name:
        return False, "보스를 선택해주세요."

    if not difficulty:
        return False, "난이도를 선택해주세요."

    count = int(st.session_state.get("party_count", 1))

    parties = []
    total_members = 0

    for i in range(1, count + 1):
        members = list(st.session_state.get(f"party_members_{i}", []))
        parties.append(members)
        total_members += len(members)

    if total_members == 0:
        return False, "파티원을 한 명 이상 선택해주세요."

    display_name = f"{difficulty} {boss_name}"

    st.session_state.completed_bosses[display_name] = {
        "boss": boss_name,
        "difficulty": difficulty,
        "display_name": display_name,
        "party_count": count,
        "parties": parties,
    }

    st.session_state["show_final_result"] = False
    return True, display_name


# =========================================================
# 최종 텍스트
# =========================================================
def build_final_text():
    lines = [
        "해피하우스 보스 파티 편성표",
        "=" * 32,
        "",
    ]

    for display_name, boss_data in st.session_state.completed_bosses.items():
        lines.append(f"[{display_name}]")

        for members in boss_data["parties"]:
            if not members:
                continue

            names = [character_lookup[cid]["nickname"] for cid in members]
            total_combat, avg_hexa = calculate_party_stats(members)

            lines.append(" - " + " / ".join(names))
            lines.append(
                "   "
                f"총 전투력 {format_combat_power(total_combat)}"
                " | "
                f"평균 헥사 {format_hexa(avg_hexa)}"
            )

        lines.append("")

    return "\n".join(lines)


# =========================================================
# 최종 파티 PNG
# =========================================================
def make_party_image():
    completed = st.session_state.completed_bosses
    if not completed:
        return None

    canvas_width = 1600
    outer_padding = 50
    top_header_height = 140
    card_gap = 28

    card_width = (canvas_width - outer_padding * 2 - card_gap) // 2

    boss_header_h = 56
    card_inner_top = 18
    card_inner_bottom = 18
    party_gap = 10

    title_font, boss_font, member_font, stat_font = load_party_fonts()

    temp_image = Image.new("RGB", (canvas_width, 300), (8, 15, 25))
    temp_draw = ImageDraw.Draw(temp_image)

    def wrap_names(text, font, max_width):
        names = text.split(" / ")
        if not names:
            return [""]

        lines = []
        current = names[0]

        for name in names[1:]:
            candidate = current + " / " + name
            bbox = temp_draw.textbbox((0, 0), candidate, font=font)
            width = bbox[2] - bbox[0]

            if width <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = name

        lines.append(current)
        return lines

    boss_cards = []
    usable_text_width = card_width - 72

    for display_name, boss_data in completed.items():
        party_rows = []

        for members in boss_data["parties"]:
            if not members:
                continue

            names = [character_lookup[cid]["nickname"] for cid in members]
            member_text = " / ".join(names)

            wrapped_lines = wrap_names(member_text, member_font, usable_text_width)[:2]
            total_combat, avg_hexa = calculate_party_stats(members)

            stat_text = (
                f"총 전투력 {format_combat_power(total_combat)}"
                "   ·   "
                f"평균 헥사환산 {format_hexa(avg_hexa)}"
            )

            row_height = 72 if len(wrapped_lines) == 1 else 96

            party_rows.append(
                {
                    "lines": wrapped_lines,
                    "stat_text": stat_text,
                    "height": row_height,
                }
            )

        if not party_rows:
            continue

        card_height = (
            card_inner_top
            + boss_header_h
            + 14
            + sum(row["height"] for row in party_rows)
            + party_gap * max(0, len(party_rows) - 1)
            + card_inner_bottom
        )

        boss_cards.append(
            {
                "boss_name": display_name,
                "rows": party_rows,
                "height": card_height,
            }
        )

    if not boss_cards:
        return None

    row_heights = []

    for i in range(0, len(boss_cards), 2):
        left_height = boss_cards[i]["height"]
        if i + 1 < len(boss_cards):
            right_height = boss_cards[i + 1]["height"]
        else:
            right_height = 0

        row_heights.append(max(left_height, right_height))

    canvas_height = (
        top_header_height
        + outer_padding
        + sum(row_heights)
        + card_gap * max(0, len(row_heights) - 1)
        + outer_padding
    )

    image = Image.new("RGB", (canvas_width, canvas_height), (8, 15, 25))
    draw = ImageDraw.Draw(image)

    draw.rectangle(
        [0, 0, canvas_width, top_header_height],
        fill=(19, 34, 55),
    )

    draw.text(
        (60, 44),
        "해피하우스 보스 파티 편성표",
        font=title_font,
        fill=(245, 249, 255),
    )

    def draw_boss_card(x, y, card_data):
        card_height = card_data["height"]

        draw.rounded_rectangle(
            [x, y, x + card_width, y + card_height],
            radius=20,
            fill=(17, 28, 43),
            outline=(78, 118, 170),
            width=2,
        )

        draw.rounded_rectangle(
            [x + 16, y + 16, x + card_width - 16, y + 16 + boss_header_h],
            radius=14,
            fill=(25, 40, 62),
            outline=(67, 111, 164),
            width=1,
        )

        draw.text(
            (x + 34, y + 29),
            card_data["boss_name"],
            font=boss_font,
            fill=(247, 250, 255),
        )

        current_y = y + 16 + boss_header_h + 14

        for row_data in card_data["rows"]:
            row_height = row_data["height"]

            draw.rounded_rectangle(
                [x + 20, current_y, x + card_width - 20, current_y + row_height],
                radius=12,
                fill=(13, 23, 36),
                outline=(43, 64, 91),
                width=1,
            )

            text_x = x + 36
            text_y = current_y + 10

            for line in row_data["lines"]:
                draw.text(
                    (text_x, text_y),
                    line,
                    font=member_font,
                    fill=(228, 237, 249),
                )
                text_y += 28

            stat_y = current_y + row_height - 26

            draw.text(
                (text_x, stat_y),
                row_data["stat_text"],
                font=stat_font,
                fill=(132, 154, 183),
            )

            current_y += row_height + party_gap

    current_y = top_header_height + outer_padding
    card_index = 0

    for row_height in row_heights:
        left_x = outer_padding
        draw_boss_card(left_x, current_y, boss_cards[card_index])
        card_index += 1

        if card_index < len(boss_cards):
            right_x = outer_padding + card_width + card_gap
            draw_boss_card(right_x, current_y, boss_cards[card_index])
            card_index += 1

        current_y += row_height + card_gap

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)

    return buffer.getvalue()


# =========================================================
# 저장 메시지
# =========================================================
if st.session_state.get("boss_hope_saved_message"):
    st.success(st.session_state["boss_hope_saved_message"])
    st.session_state["boss_hope_saved_message"] = ""


# =========================================================
# 스펙 변경 관리자
# =========================================================
if "spec_admin_ok" not in st.session_state:
    st.session_state["spec_admin_ok"] = False

with st.sidebar.expander("🔐 스펙 변경 관리자", expanded=False):
    if st.session_state["spec_admin_ok"]:
        st.success("관리자 모드")
        st.caption(f"미확인 요청 {len(pending_spec_request_nicknames)}건")
        if st.button("관리자 모드 종료", key="spec_admin_logout", use_container_width=True):
            st.session_state["spec_admin_ok"] = False
            st.rerun()
    elif ADMIN_PASSWORD:
        admin_password_input = st.text_input(
            "관리자 비밀번호",
            type="password",
            key="spec_admin_password_input",
            placeholder="관리자 비밀번호",
            label_visibility="collapsed",
        )
        if st.button("관리자 로그인", key="spec_admin_login", use_container_width=True):
            if admin_password_input == ADMIN_PASSWORD:
                st.session_state["spec_admin_ok"] = True
                st.rerun()
            else:
                st.error("관리자 비밀번호가 틀렸습니다.")
    else:
        st.caption("Secrets에 ADMIN_PASSWORD를 설정하면 관리자 확인 기능을 사용할 수 있습니다.")

if st.session_state.get("spec_request_message"):
    st.success(st.session_state["spec_request_message"] )
    del st.session_state["spec_request_message"]

if st.session_state.get("spec_confirm_message"):
    st.success(st.session_state["spec_confirm_message"] )
    del st.session_state["spec_confirm_message"]


# =========================================================
# 메뉴
# =========================================================
page = st.radio(
    "메뉴",
    ["👥 캐릭터 목록", "⚔️ 보스 파티 만들기"],
    horizontal=True,
    label_visibility="collapsed",
    key="main_page",
)


# =========================================================
# 캐릭터 목록
# =========================================================
if page == "👥 캐릭터 목록":
    if st.session_state.get("spec_admin_ok") and pending_spec_request_rows:
        with st.expander(
            f"🔔 스펙 변경 확인 필요 {len(pending_spec_request_rows)}건",
            expanded=True,
        ):
            for request_index, request_data in enumerate(pending_spec_request_rows):
                request_nickname = request_data["닉네임"]
                requested_at = request_data["요청일시"]
                info_col, action_col = st.columns([3, 1])

                with info_col:
                    st.markdown(f"**{request_nickname}**")
                    if requested_at:
                        st.caption(f"요청: {requested_at}")

                with action_col:
                    if st.button(
                        "✅ 확인 완료",
                        key=f"confirm_spec_{request_index}_{request_nickname}",
                        use_container_width=True,
                    ):
                        updated_count = confirm_spec_change(request_nickname)
                        if updated_count:
                            st.session_state["spec_confirm_message"] = (
                                f"{request_nickname}의 스펙 변경 확인을 완료했습니다."
                            )
                        st.rerun()

    server_values = []

    if "서버" in df.columns:
        for value in df["서버"].tolist():
            value = clean(value)
            if value and value not in server_values:
                server_values.append(value)

    filter_labels = [f"전체 ({len(df)})"]
    filter_map = {f"전체 ({len(df)})": "전체"}

    for server in server_values:
        count = (
            df["서버"]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq(server)
            .sum()
        )

        label = f"{server} ({count})"
        filter_labels.append(label)
        filter_map[label] = server

    selected_label = st.radio(
        "서버별 보기",
        filter_labels,
        horizontal=True,
        key="server_filter",
    )

    selected_server = filter_map[selected_label]

    if selected_server == "전체":
        filtered_df = df.copy()
    else:
        filtered_df = df[
            df["서버"].fillna("").astype(str).str.strip() == selected_server
        ].copy()

    CARDS_PER_ROW = 3

    for start in range(0, len(filtered_df), CARDS_PER_ROW):
        cols = st.columns(CARDS_PER_ROW, gap="medium")
        rows = filtered_df.iloc[start:start + CARDS_PER_ROW]

        for col, (_, row) in zip(cols, rows.iterrows()):
            with col:
                cid = int(row["_캐릭터ID"])
                nickname = clean(row.get("닉네임", ""))

                st.markdown(build_card(row), unsafe_allow_html=True)

                button_col1, button_col2 = st.columns(2)

                with button_col1:
                    if st.button(
                        "✏️ 보스희망 수정",
                        key=f"edit_hope_{cid}",
                        use_container_width=True,
                    ):
                        if st.session_state["editing_hope_nickname"] == nickname:
                            st.session_state["editing_hope_nickname"] = None
                            st.rerun()
                        else:
                            initialize_hope_editor(cid, nickname)
                            st.rerun()

                with button_col2:
                    card_png = build_character_card_image(row)

                    st.download_button(
                        "📸 카드 저장",
                        data=card_png,
                        file_name=f"{nickname}_캐릭터카드.png",
                        mime="image/png",
                        key=f"download_card_{cid}",
                        use_container_width=True,
                    )

                if st.session_state["editing_hope_nickname"] == nickname:
                    render_hope_editor(cid, nickname)

                boss_url = clean(row.get("보스배율캡처URL", ""))
                if boss_url:
                    with st.expander("📊 보스배율 보기", expanded=False):
                        boss_image = load_image_bytes(boss_url)

                        if boss_image:
                            st.image(BytesIO(boss_image), use_container_width=True)
                        else:
                            st.warning("이미지를 불러오지 못했습니다.")

                st.write("")


# =========================================================
# 보스 파티 만들기
# =========================================================
else:
    if "party_completed_message" in st.session_state:
        st.success(st.session_state["party_completed_message"])
        del st.session_state["party_completed_message"]

    st.markdown(
        """
<div class="party-page-title">
⚔️ 보스 파티 만들기
</div>

<div class="party-description">
보스와 난이도를 선택한 뒤 파티를 편성하세요.
한 보스 편성이 끝나면 완료 처리한 뒤 다음 보스를 계속 편성할 수 있습니다.
</div>
""",
        unsafe_allow_html=True,
    )

    boss_col, difficulty_col, count_col = st.columns([2, 1, 1])

    with boss_col:
        selected_boss = st.selectbox(
            "보스",
            options=list(BOSS_DIFFICULTIES.keys()),
            key="party_boss_name",
        )

    difficulty_options = BOSS_DIFFICULTIES[selected_boss]

    if "party_boss_difficulty" in st.session_state:
        if st.session_state["party_boss_difficulty"] not in difficulty_options:
            del st.session_state["party_boss_difficulty"]

    with difficulty_col:
        st.selectbox(
            "난이도",
            options=difficulty_options,
            key="party_boss_difficulty",
        )

    with count_col:
        st.selectbox(
            "파티 수",
            options=list(range(1, 11)),
            key="party_count",
        )

    selected_difficulty = st.session_state.get("party_boss_difficulty", "")
    exact_hope_candidates, other_hope_candidates = get_boss_hope_candidates(
        selected_boss,
        selected_difficulty,
    )

    currently_assigned = set()
    for party_number in range(1, st.session_state.party_count + 1):
        currently_assigned.update(
            st.session_state.get(f"party_members_{party_number}", [])
        )

    unassigned_exact = [
        candidate
        for candidate in exact_hope_candidates
        if candidate["cid"] not in currently_assigned
    ]

    st.markdown(
        f"""
<div class="party-section-title">
🎯 {html.escape(selected_difficulty)} {html.escape(selected_boss)} 희망자
</div>
""",
        unsafe_allow_html=True,
    )

    if exact_hope_candidates:
        st.caption(
            f"총 {len(exact_hope_candidates)}명 희망 · "
            f"현재 미편성 {len(unassigned_exact)}명"
        )

        if unassigned_exact:
            candidate_by_id = {
                candidate["cid"]: candidate
                for candidate in unassigned_exact
            }
            candidate_ids = list(candidate_by_id.keys())

            selected_hope_ids = st.multiselect(
                "희망자 선택",
                options=candidate_ids,
                format_func=lambda cid: hope_candidate_text(candidate_by_id[cid]),
                key=f"hope_pick_{selected_boss}_{selected_difficulty}",
                placeholder="파티에 넣을 희망자를 선택하세요",
                label_visibility="collapsed",
            )

            add_col1, add_col2 = st.columns([1.5, 1])

            with add_col1:
                target_party = st.selectbox(
                    "추가할 파티",
                    options=list(range(1, st.session_state.party_count + 1)),
                    format_func=lambda x: f"{x}파티",
                    key=f"hope_target_party_{st.session_state.party_count}",
                )

            with add_col2:
                st.write("")
                st.write("")

                if st.button(
                    "➕ 선택한 희망자 추가",
                    key=f"add_hope_to_party_{selected_boss}_{selected_difficulty}",
                    use_container_width=True,
                ):
                    if not selected_hope_ids:
                        st.warning("추가할 희망자를 먼저 선택해주세요.")
                    else:
                        member_key = f"party_members_{target_party}"
                        current_members = list(st.session_state.get(member_key, []))

                        other_party_members = set()
                        for party_number in range(1, st.session_state.party_count + 1):
                            if party_number == target_party:
                                continue
                            other_party_members.update(
                                st.session_state.get(f"party_members_{party_number}", [])
                            )

                        addable_ids = [
                            cid
                            for cid in selected_hope_ids
                            if cid not in current_members
                            and cid not in other_party_members
                        ]

                        remaining_slots = max(0, 6 - len(current_members))
                        added_ids = addable_ids[:remaining_slots]

                        if added_ids:
                            st.session_state[member_key] = current_members + added_ids

                        skipped_count = len(addable_ids) - len(added_ids)
                        if skipped_count > 0:
                            st.session_state["hope_add_message"] = (
                                f"{len(added_ids)}명을 {target_party}파티에 추가했습니다. "
                                f"정원 6명 때문에 {skipped_count}명은 추가하지 못했습니다."
                            )
                        elif added_ids:
                            st.session_state["hope_add_message"] = (
                                f"{len(added_ids)}명을 {target_party}파티에 추가했습니다."
                            )
                        else:
                            st.session_state["hope_add_message"] = (
                                "선택한 희망자는 이미 다른 파티에 편성되어 있습니다."
                            )

                        st.rerun()
        else:
            st.success("이 난이도를 희망한 사람은 모두 현재 파티에 편성되어 있습니다.")
    else:
        st.info("이 보스와 난이도를 희망한 사람이 아직 없습니다.")

    if st.session_state.get("hope_add_message"):
        st.info(st.session_state["hope_add_message"])
        del st.session_state["hope_add_message"]

    if other_hope_candidates:
        with st.expander(
            f"같은 보스의 다른 난이도 희망자 {len(other_hope_candidates)}명 보기",
            expanded=False,
        ):
            for candidate in other_hope_candidates:
                st.write("• " + other_hope_text(candidate))

    st.divider()

    selected_in_previous_parties = set()

    for party_number in range(1, st.session_state.party_count + 1):
        key = f"party_members_{party_number}"

        current_value = list(st.session_state.get(key, []))
        cleaned_value = [
            cid for cid in current_value
            if cid not in selected_in_previous_parties
        ]

        if current_value != cleaned_value:
            st.session_state[key] = cleaned_value

        available_ids = [
            cid for cid in all_character_ids
            if cid not in selected_in_previous_parties or cid in cleaned_value
        ]

        st.markdown(
            f"""
<div class="party-section-title">
{party_number}파티
</div>
""",
            unsafe_allow_html=True,
        )

        selected_members = st.multiselect(
            f"{party_number}파티",
            options=available_ids,
            format_func=character_option_text,
            key=key,
            max_selections=6,
            placeholder="파티원을 선택하세요",
            label_visibility="collapsed",
        )

        selected_in_previous_parties.update(selected_members)

        if selected_members:
            total_combat, avg_hexa = calculate_party_stats(selected_members)

            m1, m2, m3 = st.columns(3)

            with m1:
                st.metric("인원", f"{len(selected_members)}명")
            with m2:
                st.metric("총 전투력", format_combat_power(total_combat))
            with m3:
                st.metric("평균 헥사환산", format_hexa(avg_hexa))

    st.write("")

    exact_candidate_ids = {
        candidate["cid"]
        for candidate in exact_hope_candidates
    }
    assigned_candidate_ids = set()
    for party_number in range(1, st.session_state.party_count + 1):
        assigned_candidate_ids.update(
            st.session_state.get(f"party_members_{party_number}", [])
        )

    unassigned_candidate_ids = exact_candidate_ids - assigned_candidate_ids

    if exact_candidate_ids:
        if unassigned_candidate_ids:
            unassigned_names = [
                character_lookup[cid]["nickname"]
                for cid in exact_candidate_ids
                if cid in unassigned_candidate_ids
            ]
            st.warning(
                "⚠️ 아직 편성되지 않은 희망자: "
                + ", ".join(unassigned_names)
            )
        else:
            st.success("✅ 이 보스·난이도의 희망자가 모두 편성되었습니다.")

    if st.button(
        "✅ 이 보스 편성 완료",
        use_container_width=True,
        type="primary",
        key="complete_current_boss",
    ):
        success, result = save_current_boss()

        if success:
            display_name = result
            st.session_state["pending_clear_party_editor"] = True
            st.session_state["party_completed_message"] = f"{display_name} 편성이 완료되었습니다."
            st.rerun()
        else:
            st.warning(result)

    if st.session_state.completed_bosses:
        st.divider()

        st.markdown(
            """
<div class="party-section-title">
📚 완료된 보스 편성
</div>
""",
            unsafe_allow_html=True,
        )

        completed_items = list(st.session_state.completed_bosses.items())

        for index, (display_name, boss_data) in enumerate(completed_items):
            used_parties = sum(1 for party in boss_data["parties"] if party)
            member_count = sum(len(party) for party in boss_data["parties"])

            completed_html = "".join([
                '<div class="completed-boss">',
                '<div class="completed-boss-title">',
                f'⚔️ {html.escape(display_name)}',
                '</div>',
                '<div class="completed-boss-info">',
                f'{used_parties}개 파티 · 총 편성 {member_count}명',
                '</div>',
                '</div>',
            ])

            st.markdown(completed_html, unsafe_allow_html=True)

            c1, c2 = st.columns(2)

            with c1:
                if st.button(
                    "✏️ 불러오기 / 수정",
                    key=f"load_boss_{index}",
                    use_container_width=True,
                ):
                    st.session_state["pending_load_boss"] = display_name
                    st.rerun()

            with c2:
                if st.button(
                    "🗑️ 삭제",
                    key=f"delete_boss_{index}",
                    use_container_width=True,
                ):
                    del st.session_state.completed_bosses[display_name]
                    st.session_state["show_final_result"] = False
                    st.rerun()

        st.divider()

        if st.button(
            "🏁 전체 파티 구성 완료",
            type="primary",
            use_container_width=True,
            key="finish_all_parties",
        ):
            st.session_state["show_final_result"] = True
            st.rerun()

    if st.session_state.show_final_result and st.session_state.completed_bosses:
        st.divider()

        st.markdown(
            """
<div class="party-page-title">
🏆 해피하우스 보스 파티 편성표
</div>
""",
            unsafe_allow_html=True,
        )

        for display_name, boss_data in st.session_state.completed_bosses.items():
            final_parts = [
                '<div class="final-boss-card">',
                '<div class="final-boss-name">',
                f'⚔️ {html.escape(display_name)}',
                '</div>',
            ]

            for members in boss_data["parties"]:
                if not members:
                    continue

                names = [
                    html.escape(character_lookup[cid]["nickname"])
                    for cid in members
                ]

                total_combat, avg_hexa = calculate_party_stats(members)

                final_parts.extend([
                    '<div class="final-party-line">',
                    " / ".join(names),
                    '<div class="final-party-stat">',
                    f'총 전투력 {format_combat_power(total_combat)}',
                    '&nbsp;&nbsp;·&nbsp;&nbsp;',
                    f'평균 헥사 {format_hexa(avg_hexa)}',
                    '</div>',
                    '</div>',
                ])

            final_parts.append('</div>')

            st.markdown("".join(final_parts), unsafe_allow_html=True)

        final_text = build_final_text()

        with st.expander("📋 텍스트 결과 보기"):
            st.code(final_text, language=None)

        png_bytes = make_party_image()

        if png_bytes:
            st.image(
                png_bytes,
                caption="최종 파티 편성 이미지",
                use_container_width=True,
            )

            st.download_button(
                "🖼️ 파티 편성표 이미지 저장",
                data=png_bytes,
                file_name="해피하우스_보스파티_편성표.png",
                mime="image/png",
                use_container_width=True,
            )
