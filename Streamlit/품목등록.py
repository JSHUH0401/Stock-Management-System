import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from supabase import create_client, Client

# 1. Supabase 연결
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def init_connection():
    return create_client(url, key)

supabase = init_connection()

def admin_management_page():
    st.title("🔐 시스템 마스터 관리자")
    
    tab1, tab2 = st.tabs(["🆕 신규 품목/공급처 등록", "🛠️ DB 테이블 직접 수정"])

    # ---------------------------------------------------------
    # TAB 1: 신규 등록 (입력 검증 및 순서 조정)
    # ---------------------------------------------------------
    with tab1:
        st.subheader("1️⃣ 공급처 및 품목 통합 등록")
        
        # 기존 공급처 목록 로드
        res_sup = supabase.table("SUPPLIERS").select("id, name").execute()
        sup_dict = {s['name']: s['id'] for s in res_sup.data}
        sup_list = ["+ 신규 공급처 직접 입력"] + list(sup_dict.keys())
        
        with st.form("new_registration_form", clear_on_submit=False):
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("### **기본 정보**")
                sel_sup = st.selectbox("공급처 선택", options=sup_list)
                new_sup_name = st.text_input("신규 공급처 이름 (신규 선택 시 필수)")
                item_name = st.text_input("품목 이름 (예: 원두 1kg)")
                category = st.text_input("카테고리 (예: 커피재료)")

            with c2:
                st.markdown("### **발주 설정**")
                order_url = st.text_input("주문 URL (선택 사항)")
                order_unit = st.text_input("주문 단위 (예: 박스, 팩)")
                moq = st.number_input("MOQ (최소 주문 수량)", min_value=1, value=1)
                unit_price = st.number_input("주문 단위당 가격 (원)", min_value=0, step=100)

            st.divider() # --- 구분선 ---
            
            st.markdown("### **재고 및 단위 환산 설정**")
            cc1, cc2, cc3 = st.columns(3)
            # 사장님 요청 순서: 재고관리단위 -> 환산계수 -> 안전재고
            base_unit = cc1.text_input("재고 관리 단위 (예: 개, g, ml)")
            conv_factor = cc2.number_input("환산 계수 (1주문단위당 낱개 수)", min_value=1, value=1)
            safety_stock = cc3.number_input("안전재고 (낱개 기준)", min_value=0)

            if st.form_submit_button("전체 데이터 등록 실행", type="primary"):
                # --- [필수 값 검증 로직] ---
                # URL을 제외한 모든 필드가 채워졌는지 확인
                is_sup_valid = (sel_sup != "+ 신규 공급처 직접 입력") or (sel_sup == "+ 신규 공급처 직접 입력" and new_sup_name)
                required_fields = [item_name, category, order_unit, base_unit]
                
                if not all(required_fields) or not is_sup_valid:
                    st.error("🚨 오류: 주문 URL을 제외한 모든 항목을 정확히 입력해주세요.")
                else:
                    try:
                        # STEP 1: 공급처(SUPPLIERS) ID 확보
                        if sel_sup == "+ 신규 공급처 직접 입력":
                            ex_sup = supabase.table("SUPPLIERS").select("id").eq("name", new_sup_name).execute()
                            if ex_sup.data:
                                target_sup_id = ex_sup.data[0]['id']
                            else:
                                sup_res = supabase.table("SUPPLIERS").insert({"name": new_sup_name}).execute()
                                target_sup_id = sup_res.data[0]['id']
                        else:
                            target_sup_id = sup_dict[sel_sup]

                        # STEP 2: 품목(ITEMS) ID 확보
                        ex_itm = supabase.table("ITEMS").select("id").eq("name", item_name).execute()
                        if ex_itm.data:
                            target_item_id = ex_itm.data[0]['id']
                        else:
                            itm_res = supabase.table("ITEMS").insert({"name": item_name, "category": category}).execute()
                            target_item_id = itm_res.data[0]['id']

                        # STEP 3: 상세정보(SUPPLIER_DETAILS) 등록
                        supabase.table("SUPPLIER_DETAILS").upsert({
                            "item_id": target_item_id,
                            "supplier_id": target_sup_id,
                            "order_url": order_url,
                            "order_unit": order_unit,
                            "MOQ": moq,
                            "order_unit_price": unit_price,
                            "safety_stock": safety_stock,
                            "base_unit": base_unit,
                            "conversion_factor": conv_factor
                        }).execute()

                        # STEP 4: 재고(STOCKS) 초기화
                        ex_stk = supabase.table("STOCKS").select("*").match({"item_id": target_item_id, "supplier_id": target_sup_id}).execute()
                        if not ex_stk.data:
                            supabase.table("STOCKS").insert({
                                "item_id": target_item_id,
                                "supplier_id": target_sup_id,
                                "stock": 0,
                                "avg_consumption": 0,
                                "last_checked_at": datetime.now(timezone.utc).isoformat()
                            }).execute()

                        st.success(f"✅ '{item_name}' 등록이 완료되었습니다!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"❌ 등록 중 오류 발생: {e}")

    # ---------------------------------------------------------
    # TAB 2: DB 직접 수정 (가불기 테이블 에디터)
    # ---------------------------------------------------------
    with tab2:
        st.subheader("🛠️ DB 테이블 즉시 편집")
        target_tab = st.selectbox("수정할 테이블 선택", ["ITEMS", "STOCKS", "SUPPLIERS", "SUPPLIER_DETAILS", "PURCHASE_ORDERS", "PURCHASE_ITEMS"])
        
        res = supabase.table(target_tab).select("*").execute()
        df = pd.DataFrame(res.data)
        
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"admin_editor_{target_tab}")
        
        if st.button(f"{target_tab} 데이터 반영", type="primary"):
            try:
                updated_data = edited_df.to_dict(orient='records')
                supabase.table(target_tab).upsert(updated_data).execute()
                st.success(f"✅ {target_tab} 업데이트 성공!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 반영 실패: {e}")

if __name__ == "__main__":
    admin_management_page()