import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# 1. 초기 설정 및 타임존 (KST)
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
KST = timezone(timedelta(hours=9))

@st.cache_resource
def init_connection():
    return create_client(url, key)

supabase = init_connection()

# --- [도우미 함수: 요일 가중치 계산] ---
def get_total_weight(start_date, end_date):
    """두 날짜 사이의 소모 가중치 합계 계산"""
    weekday_factors = {0: 0.8, 4: 1.2, 5: 1.5, 6: 1.3}
    total_weight = 0
    current = start_date.astimezone(timezone.utc)
    now = end_date.astimezone(timezone.utc)
    
    temp_date = current
    while temp_date <= now:
        factor = weekday_factors.get(temp_date.weekday(), 1.0)
        total_weight += factor
        temp_date += timedelta(days=1)
    return total_weight

# --- [데이터 로드: 재고 및 안전재고] ---
def get_dashboard_data():
    res_stock = supabase.table("STOCKS").select("*, ITEMS(name)").execute()
    df_stock = pd.DataFrame(res_stock.data)
    if 'ITEMS' in df_stock.columns:
        df_stock['item_name'] = df_stock['ITEMS'].apply(lambda x: x.get('name') if isinstance(x, dict) else "N/A")
    
    res_details = supabase.table("SUPPLIER_DETAILS").select("item_id, supplier_id, safety_stock, base_unit").execute()
    df_details = pd.DataFrame(res_details.data)

    merged_df = pd.merge(df_stock, df_details, on=['item_id', 'supplier_id'], how='left')
    return merged_df.loc[:, ~merged_df.columns.duplicated()]

# --- [데이터 로드: 배송 현황 및 환산 계수] ---
def get_shipping_orders():
    # 1. 배송중 주문 마스터
    res_orders = supabase.table("PURCHASE_ORDERS").select("*, SUPPLIERS(name)").eq("status", "배송중").execute()
    df_orders = pd.DataFrame(res_orders.data)
    
    if df_orders.empty:
        return pd.DataFrame(), pd.DataFrame()

    df_orders['supplier_name'] = df_orders['SUPPLIERS'].apply(lambda x: x.get('name') if isinstance(x, dict) else "N/A")
    active_ids = df_orders['order_id'].tolist()

    # 2. 상세 품목 로드
    res_items = supabase.table("PURCHASE_ITEMS").select("order_id, item_id, actual_qty, ITEMS(name)").in_("order_id", active_ids).execute()
    df_items = pd.DataFrame(res_items.data)
    
    if not df_items.empty:
        df_items['품목명'] = df_items['ITEMS'].apply(lambda x: x.get('name') if isinstance(x, dict) else "N/A")
        
        # 3. [중요] 단가 및 환산 계수(conversion_factor) 정보 병합
        res_details = supabase.table("SUPPLIER_DETAILS").select("item_id, supplier_id, order_unit_price, conversion_factor").execute()
        df_details = pd.DataFrame(res_details.data)
        
        df_items = pd.merge(df_items, df_orders[['order_id', 'supplier_id']], on='order_id', how='left')
        df_items = pd.merge(df_items, df_details, on=['item_id', 'supplier_id'], how='left')

    return df_orders, df_items

# --- [메인 UI 시작] ---
st.set_page_config(page_title="재고 관리 대시보드", layout="wide")
st.title("🚨 실시간 재고 모니터링")

df = get_dashboard_data()
now_kst = datetime.now(KST)

# 3. 예상 재고 계산 및 표시
predicted_results = []
for index, row in df.iterrows():
    last_checked = pd.to_datetime(row['last_checked_at']).tz_convert('Asia/Seoul')
    weight_sum = get_total_weight(last_checked, now_kst)
    
    reduction = row['avg_consumption'] * weight_sum
    predicted_stock = max(0, row['stock'] - reduction)
    
    predicted_results.append({
        "품목명": row['item_name'],
        "현재 예상 재고": round(predicted_stock, 2),
        "안전재고": row['safety_stock'],
        "단위": row['base_unit'],
        "상태": "🔴 발주필요" if predicted_stock < row['safety_stock'] else "🟢 안정"
    })

res_df = pd.DataFrame(predicted_results)
danger_df = res_df[res_df['상태'] == "🔴 발주필요"]

c1, c2 = st.columns(2)
c1.metric("전체 품목", len(res_df))
c2.metric("발주 필요", len(danger_df), delta_color="inverse")

st.divider()

if not danger_df.empty:
    st.subheader("⚠️ 안전재고 미달 품목")
    st.dataframe(danger_df, use_container_width=True, hide_index=True)
else:
    st.success("✅ 모든 품목의 재고가 충분합니다.")

# 🚚 배송 현황 섹션 (단위 환산 적용)
st.divider()
st.subheader("🚚 배송 중인 주문 현황")

orders, items = get_shipping_orders()

if orders.empty:
    st.info("현재 배송 중인 내역이 없습니다.")
else:
    for _, order in orders.iterrows():
        oid = order['order_id']
        s_name = order['supplier_name']
        
        col_info, col_btn = st.columns([5, 1])
        with col_info:
            expander_label = f"📦 주문 #{oid} | 공급처: {s_name} (총 {order['total_price']:,}원)"
            exp = st.expander(expander_label, expanded=False)
            
        with col_btn:
            st.write("<div style='height: 5px;'></div>", unsafe_allow_html=True)
            if st.button("입고완료", key=f"done_{oid}", use_container_width=True):
                with st.spinner("재고 업데이트 중..."):
                    try:
                        order_items = items[items['order_id'] == oid]
                        for _, item in order_items.iterrows():
                            # [핵심] DB에서 현재 stock 조회
                            res = supabase.table("STOCKS").select("stock").match({
                                "item_id": item['item_id'], 
                                "supplier_id": item['supplier_id']
                            }).execute()
                            
                            if res.data:
                                current_db_stock = res.data[0]['stock']
                                
                                # [수정] 발주수량(묶음) * 환산계수 = 실제 입고 개수
                                cf = item['conversion_factor'] if pd.notnull(item['conversion_factor']) else 1
                                received_real_qty = item['actual_qty'] * cf
                                
                                # 원본 stock에 더하기 (last_checked_at은 유지)
                                new_db_stock = current_db_stock + received_real_qty
                                
                                supabase.table("STOCKS").update({
                                    "stock": float(new_db_stock)
                                }).match({
                                    "item_id": item['item_id'], 
                                    "supplier_id": item['supplier_id']
                                }).execute()

                        supabase.table("PURCHASE_ORDERS").update({"status": "입고완료"}).eq("order_id", oid).execute()
                        st.toast(f"✅ #{oid} 입고 완료 (단위 환산 적용됨)")
                        st.rerun()
                    except Exception as e:
                        st.error(f"오류: {e}")
        
        with exp:
            detail = items[items['order_id'] == oid]
            if not detail.empty:
                display_df = detail[['품목명', 'actual_qty', 'conversion_factor', 'order_unit_price']].copy()
                # 사용자 이해를 돕기 위해 입고예정량(환산후) 컬럼 추가 표시
                display_df['입고예정량'] = display_df['actual_qty'] * display_df['conversion_factor'].fillna(1)
                display_df.columns = ['품목명', '주문수량(묶음)', '환산계수', '단가', '입고예정량(개)']
                
                st.table(display_df.style.format({
                    "주문수량(묶음)": "{:,.0f}",
                    "환산계수": "x{:,.0f}",
                    "단가": "{:,.0f}원",
                    "입고예정량(개)": "{:,.0f}"
                }))