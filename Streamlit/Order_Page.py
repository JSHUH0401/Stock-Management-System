import streamlit as st

# --- [1] 세션 상태 초기화 (모든 변수를 한 곳에서!) ---
def init_session_state():
    if 'show_toast' not in st.session_state:
        st.session_state.show_toast = False
    if 'order_mode' not in st.session_state:
        st.session_state.order_mode = "추천"
    if 'manual_cart' not in st.session_state:
        st.session_state.manual_cart = {}
    # Supabase 연결 후에는 item_master도 여기서 load_data()로 호출하면 좋습니다.


init_session_state()

# --- [2] 토스트 메시지 출력 (안전하게 .get 사용) ---
if st.session_state.get('show_toast', False):
    st.toast("발주 완료 처리되었습니다.")
    st.session_state.show_toast = False
    
# 1. 초기 데이터 설정 [cite: 17, 21]
if 'item_master' not in st.session_state:
    st.session_state.item_master = [
        {"item_name": "원두 (에스프레소)", "suppliers": ["A커피", "B커피"], "current_stock": 5, "safety_stock": 10, "unit": 1, "prices": {"A커피": 15000, "B커피": 16000}, "urls": {"A커피": "https://search.naver.com", "B커피": "https://www.coupang.com"}},
        {"item_name": "바닐라 시럽", "suppliers": ["A커피"], "current_stock": 2, "safety_stock": 5, "unit": 6, "prices": {"A커피": 8000}, "urls": {"A커피": "https://www.google.com"}},
        {"item_name": "우유 (1L)", "suppliers": ["B유업"], "current_stock": 12, "safety_stock": 20, "unit": 12, "prices": {"B유업": 2500}, "urls": {"B유업": "https://www.daum.net"}},
        {"item_name": "종이컵 (Hot)", "suppliers": ["C물산"], "current_stock": 500, "safety_stock": 300, "unit": 1000, "prices": {"C물산": 50}, "urls": {"C물산": "https://www.youtube.com"}},
    ]

# 상태 관리 변수 [cite: 19]
if 'order_mode' not in st.session_state:
    st.session_state.order_mode = "추천"
if 'manual_cart' not in st.session_state:
    st.session_state.manual_cart = {}

# CSS: 버튼 색상 변경 및 정렬 미세조정
st.markdown("""
    <style>
    /* Primary 버튼 색상을 강렬한 빨간색에서 차분한 네이비 블루로 변경 */
    div.stButton > button[kind="primary"] {
        background-color: #2E4053; 
        color: white;
        border-color: #2E4053;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #1B2631;
        border-color: #1B2631;
    }
    /* 수량 조절 버튼 크기 미세 조정 */
    .stButton button { font-size: 12px; padding: 2px 5px; }
    </style>
    """, unsafe_allow_html=True)

def order_page():
    st.title("만월경 발주 관리")
    
    # --- 1. 발주 모드 선택 영역  ---
    st.write("### 📂 발주 모드 선택")
    col_rec, col_cus = st.columns(2)
    
    with col_rec:
        rec_style = "primary" if st.session_state.order_mode == "추천" else "secondary"
        if st.button("시스템 추천 발주", use_container_width=True, type=rec_style):
            st.session_state.order_mode = "추천"
            st.session_state.manual_cart = {}
            st.rerun()

    with col_cus:
        cus_style = "primary" if st.session_state.order_mode == "커스텀" else "secondary"
        if st.button("커스텀 발주", use_container_width=True, type=cus_style):
            st.session_state.order_mode = "커스텀"
            st.session_state.manual_cart = {}
            st.rerun()

    # --- 2. 품목 직접 추가 섹션 (버튼 수평 정렬 개선) ---
    with st.container(border=True):
        st.subheader("품목 직접 추가")
        # 컬럼 비율 조정 및 버튼 위치 최적화
        c1, c2, c3 = st.columns([4, 4, 1.5])
        
        item_names = [i["item_name"] for i in st.session_state.item_master]
        sel_name = c1.selectbox("상품 선택", options=item_names, key="p_box")
        item_info = next(i for i in st.session_state.item_master if i["item_name"] == sel_name)
        
        sel_sup = c2.selectbox("공급처 선택", options=item_info["suppliers"], 
                               disabled=len(item_info["suppliers"]) == 1, key="s_box")
        
        # 버튼 수평을 맞추기 위한 빈 공간 삽입
        with c3:
            st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("리스트 추가", use_container_width=True):
                key = (sel_name, sel_sup)
                st.session_state.manual_cart[key] = st.session_state.manual_cart.get(key, 0) + item_info["unit"]
                st.rerun()

    # --- 3. 발주 목록 표시  ---
    st.write("---")
    st.subheader(f"{st.session_state.order_mode} 발주 목록")
    
    display_items = {}
    if st.session_state.order_mode == "추천":
        for item in st.session_state.item_master:
            if item["current_stock"] < item["safety_stock"]:
                sup = item["suppliers"][0]
                display_items[(item["item_name"], sup)] = st.session_state.manual_cart.get((item["item_name"], sup), item["unit"])
        display_items.update(st.session_state.manual_cart)
    else:
        display_items = st.session_state.manual_cart

    if not display_items:
        st.info("현재 발주 대기 목록이 비어 있습니다.")
    else:
        active_sups = sorted(list(set(k[1] for k in display_items.keys())))
        total_price = 0

        for sup in active_sups:
            with st.expander(f"🏢 공급처: {sup}", expanded=True):
                sup_items = {k: v for k, v in display_items.items() if k[1] == sup}
                for (name, s), qty in sup_items.items():
                    item_data = next(i for i in st.session_state.item_master if i["item_name"] == name)
                    cols = st.columns([2.5, 1.2, 3.5, 2, 1.5]) 
                    
                    cols[0].write(f"**{name}**")
                    cols[1].caption(f"재고:{item_data['current_stock']}")
                    
                    # 수량 조절 버튼 (Compact 디자인)
                    btn_col = cols[2]
                    bc1, bc2, bc3 = btn_col.columns([1, 1.2, 1])
                    if bc1.button("－", key=f"min_{name}_{sup}", use_container_width=True):
                        st.session_state.manual_cart[(name, s)] = max(0, qty - item_data["unit"])
                        st.rerun()
                    bc2.markdown(f"<div style='text-align: center; font-size: 14px; margin-top: 5px;'>{qty}</div>", unsafe_allow_html=True)
                    if bc3.button("＋", key=f"plu_{name}_{sup}", use_container_width=True):
                        st.session_state.manual_cart[(name, s)] = qty + item_data["unit"]
                        st.rerun()
                    
                    price = qty * item_data["prices"][sup]
                    cols[3].write(f"**{price:,}원**")
                    total_price += price
                    
                    # 원클릭 발주 연동 [cite: 16]
                    cols[4].link_button("🔗발주", item_data["urls"].get(sup, "#"), use_container_width=True)

        # --- 4. 최종 발주 승인 [cite: 12, 25] ---
        st.divider()
        fb1, fb2 = st.columns([2, 1])
        fb1.metric("최종 발주 합계 금액", f"{total_price:,} 원")

        if fb2.button("전체 발주 완료 처리", type="primary", use_container_width=True):
            # 공통: 메시지 표시 플래그 활성화
            st.session_state.show_toast = True
            
            if st.session_state.order_mode == "추천":
                # 추천 발주: 실제 재고 반영 및 목록 비움 [cite: 12, 25, 28]
                for (name, sup), q in display_items.items():
                    for idx, item in enumerate(st.session_state.item_master):
                        if item["item_name"] == name:
                            st.session_state.item_master[idx]["current_stock"] += q
                st.session_state.manual_cart = {} # 추천 모드는 완료 후 목록 초기화
                st.rerun()
                
            else:
                # 커스텀 발주: 목록을 비우지 않고(manual_cart 유지) 화면만 갱신 
                # st.session_state.manual_cart = {}  <-- 이 줄을 삭제하여 목록을 유지함
                st.session_state.manual_cart = {} # 추천 모드는 완료 후 목록 초기화
                st.rerun()

if __name__ == "__main__":
    order_page()
