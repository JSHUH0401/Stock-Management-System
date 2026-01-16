import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# 1. 연결 설정 (기존과 동일)
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_connection():
    return create_client(url, key)

supabase = init_connection()

# 2. 데이터 불러오기 및 병합 함수
def get_stock_data():
    # A. STOCKS와 ITEMS(name) 가져오기
    # STOCKS에는 item_id, supplier_id, stock, last_checked_at이 있음
    res_stock = supabase.table("STOCKS").select("*, ITEMS(name)").execute()
    df_stock = pd.DataFrame(res_stock.data)
    
    # ITEMS 딕셔너리에서 name 추출
    if 'ITEMS' in df_stock.columns:
        df_stock['item_name'] = df_stock['ITEMS'].apply(lambda x: x.get('name') if isinstance(x, dict) else "이름 없음")
        df_stock = df_stock.drop(columns=['ITEMS'])

    # B. SUPPLIER_DETAILS에서 단위(base_unit) 가져오기
    # unit을 위해 item_id, supplier_id, base_unit이 필요함
    res_details = supabase.table("SUPPLIER_DETAILS").select("item_id, supplier_id, base_unit").execute()
    df_details = pd.DataFrame(res_details.data)

    # C. 두 테이블 병합 (item_id와 supplier_id가 모두 일치하는 행끼리 합침)
    # 이 과정을 통해 특정 상품의 특정 공급처에 맞는 정확한 단위를 가져옵니다.
    merged_df = pd.merge(df_stock, df_details, on=['item_id', 'supplier_id'], how='left')
    
    # 시간대 처리 및 컬럼명 정리
    merged_df['last_checked_at'] = pd.to_datetime(merged_df['last_checked_at'], utc=True)
    if 'stock' in merged_df.columns:
        merged_df = merged_df.rename(columns={'stock': 'current_stock', 'base_unit': 'unit'})
        
    return merged_df

# 3. 신호등 로직 함수 (에러 수정 완료)
def get_indicator(last_date):
    if pd.isna(last_date): return "🔴"
    
    # tz-aware(UTC) 현재 시간 생성
    now = datetime.now(timezone.utc)
    # 반드시 위에서 만든 'now' 변수와 비교해야 에러가 나지 않습니다.
    diff = (now - last_date).days
    
    if diff <= 3: return "🟢"
    elif diff <= 7: return "🟡"
    else: return "🔴"

# --- 앱 UI 구성 ---
st.title("📦 재고 입력 및 상태 체크")

df = get_stock_data()

# 데이터 가공
df['상태'] = df['last_checked_at'].apply(get_indicator)
df['새로운 재고량'] = 0.0

# ERD의 컬럼명에 맞춰 display_df 구성
display_df = df[['item_id','supplier_id','상태', 'item_name', 'current_stock', 'unit', '새로운 재고량', 'last_checked_at']]

st.subheader("오늘의 재고 점검 리스트")
st.caption("🔴: 7일 이상 미점검 | 🟡: 4~7일 | 🟢: 3일 이내")

# 4. Streamlit Data Editor
edited_df = st.data_editor(
    display_df,
    column_config={
        "item_id":None,
        "supplier_id": None,
        "상태": st.column_config.TextColumn("상태", width="small"),
        "item_name": "품목명",
        "current_stock": st.column_config.NumberColumn("현재 재고", help="DB에 기록된 수량"),
        "unit": "단위",
        "새로운 재고량": st.column_config.NumberColumn("실사 재고 입력", min_value=0, step=1),
        "last_checked_at": st.column_config.DateColumn("마지막 점검일")
    },
    disabled=["상태", "item_name", "current_stock", "unit", "last_checked_at"],
    hide_index=True,
    use_container_width=True
)

# 5. 재고 반영 버튼 로직
if st.button("재고 반영하기", type="primary"):
    # 새로운 재고량이 입력된 행만 필터링
    updates = edited_df[edited_df['새로운 재고량'] > 0]
    
    if not updates.empty:
        with st.spinner("DB 업데이트 중..."):
            try:
                success_count = 0
                for index, row in updates.iterrows():
                    # 2. .match()에 들어가는 값들을 명시적으로 순수 int형으로 변환
                    target_item_id = int(row['item_id'])
                    target_supplier_id = int(row['supplier_id'])
                    
                    # 3. DB 업데이트 실행
                    response = supabase.table("STOCKS").update({
                        "stock": float(row['새로운 재고량']), # DB 타입 float8 대응
                    }).match({
                        "item_id": target_item_id,       # 정확한 매칭을 위해 int형 사용
                        "supplier_id": target_supplier_id # 정확한 매칭을 위해 int형 사용
                    }).execute()
                    
                    # 업데이트 결과 확인 (반영된 데이터가 있으면 성공)
                    if response.data:
                        success_count += 1
                
                if success_count > 0:
                    st.toast(f"✅ {success_count}개 품목의 재고가 DB에 반영되었습니다.")
                else:
                    st.warning("조건에 일치하는 데이터가 없어 업데이트되지 않았습니다. ID 값을 확인하세요.")

            except Exception as e:
                st.error(f"업데이트 중 오류가 발생했습니다: {e}")
    else:
        st.warning("입력된 새로운 재고 수량이 없습니다.")